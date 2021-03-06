# pylint: disable=no-member
import datetime
import logging
from typing import List

from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    DateField,
    FloatField,
    ForeignKey,
    Q,
    TextField,
    URLField,
)

from django_countries.fields import CountryField
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.admin.edit_handlers import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
    PageChooserPanel,
    StreamFieldPanel,
    TabbedInterface,
)
from wagtail.core.blocks import PageChooserBlock
from wagtail.core.fields import RichTextField, StreamBlock, StreamField
from wagtail.core.models import Orderable
from wagtail.images.edit_handlers import ImageChooserPanel

from ..common.blocks import AgendaItemBlock, ExternalSpeakerBlock, FeaturedExternalBlock
from ..common.constants import (
    COUNTRY_QUERYSTRING_KEY,
    DATE_PARAMS_QUERYSTRING_KEY,
    PAGINATION_QUERYSTRING_KEY,
    PAST_EVENTS_QUERYSTRING_VALUE,
    RICH_TEXT_FEATURES_SIMPLE,
    TOPIC_QUERYSTRING_KEY,
)
from ..common.fields import CustomStreamField
from ..common.models import BasePage
from ..common.utils import (
    get_combined_events,
    get_past_event_cutoff,
    paginate_resources,
)
from ..topics.models import Topic

logger = logging.getLogger(__name__)


class EventsTag(TaggedItemBase):
    content_object = ParentalKey(
        "Events", on_delete=CASCADE, related_name="tagged_items"
    )


class EventTag(TaggedItemBase):
    content_object = ParentalKey(
        "Event", on_delete=CASCADE, related_name="tagged_items"
    )


class EventTopic(Orderable):
    event = ParentalKey("Event", related_name="topics")
    topic = ForeignKey("topics.Topic", on_delete=CASCADE, related_name="+")
    panels = [PageChooserPanel("topic")]


class EventSpeaker(Orderable):
    event = ParentalKey("Event", related_name="speaker")
    speaker = ForeignKey("people.Person", on_delete=CASCADE, related_name="+")
    panels = [PageChooserPanel("speaker")]


class Events(BasePage):

    EVENTS_PER_PAGE = 8

    parent_page_types = ["home.HomePage"]
    subpage_types = ["events.Event"]
    template = "events.html"

    # Content fields
    featured = StreamField(
        StreamBlock(
            [
                (
                    "event",
                    PageChooserBlock(
                        target_model=("events.Event", "externalcontent.ExternalEvent")
                    ),
                ),
                ("external_page", FeaturedExternalBlock()),
            ],
            max_num=2,
            required=False,
        ),
        null=True,
        blank=True,
        help_text=(
            "Optional space to show featured events. Note that these are "
            "rendered two-up, so please set 0 or 2"
        ),
    )
    body = CustomStreamField(
        null=True,
        blank=True,
        help_text=(
            "Main page body content. Supports rich text, images, embed via URL, "
            "embed via HTML, and inline code snippets"
        ),
    )

    # Meta fields
    keywords = ClusterTaggableManager(through=EventsTag, blank=True)

    # Content panels
    content_panels = BasePage.content_panels + [
        StreamFieldPanel("featured"),
        StreamFieldPanel("body"),
    ]

    # Meta panels
    meta_panels = [
        MultiFieldPanel(
            [
                FieldPanel("seo_title"),
                FieldPanel("search_description"),
                ImageChooserPanel("social_image"),
                FieldPanel("keywords"),
            ],
            heading="SEO",
            help_text=(
                "Optional fields to override the default title and description "
                "for SEO purposes"
            ),
        )
    ]

    # Settings panels
    settings_panels = BasePage.settings_panels + [
        FieldPanel("slug"),
        FieldPanel("show_in_menus"),
    ]

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading="Content"),
            ObjectList(meta_panels, heading="Meta"),
            ObjectList(settings_panels, heading="Settings", classname="settings"),
        ]
    )

    class Meta:
        verbose_name_plural = "Events"

    @classmethod
    def can_create_at(cls, parent):
        # Allow only one instance of this page type
        return super().can_create_at(parent) and not cls.objects.exists()

    def get_context(self, request):
        context = super().get_context(request)
        context["filters"] = self.get_filters()
        context["events"] = self.get_events(request)
        return context

    def _pop_past_events_marker_from_date_params(self, date_params):
        """For the given list of "YYYY-MM" strings and an optional sentinel that shows
        whether we should include past events, return a list of tuples containing
        the year and and month, as unmutated strings, PLUS a separate Boolean value,
        defaulting to False.

        Example input:  ["2020-03", "2020-12"]
        Example output:  (["2020-03", "2020-12"], False)

        Example input:  ["2020-03", "2020-12", "past"]
        Example output:  (["2020-03", "2020-12"], True)
        """

        past_events_flag = bool(date_params) and (
            PAST_EVENTS_QUERYSTRING_VALUE in date_params
        )

        if past_events_flag:
            date_params.pop(date_params.index(PAST_EVENTS_QUERYSTRING_VALUE))

        return date_params, past_events_flag

    def _year_months_to_years_and_months_tuples(self, year_months):
        """For the given list of "YYYY-MM" strings, return a list of tuples
        containg the year and and month, still as strings.

        Example input:  ["2020-03", "2020-12"]
        Example output: [("2020", "03"), ("2020", "12")]
        """

        if not year_months:
            return []
        return [tuple(x.split("-")) for x in [y for y in year_months if y]]

    def _build_date_q(self, date_params):
        """Suport filtering events by selected year-month pair(s) and/or an
        'all past events' Boolean.

        Note that this method returns early, to avoid nested clauses

        Arguments:
            date_params: List(str) -- list of strings representing selected
            dates in the filtering panel, where each string is either in YYYY-MM format
            or the sentinel string PAST_EVENTS_QUERYSTRING_VALUE.

        Returns:
            django.models.QuerySet -- configured QuerySet based on arguments.
        """

        # Assemble facts from the year_months querystring data
        year_months, past_events_flag = self._pop_past_events_marker_from_date_params(  # noqa: E501
            date_params
        )
        years_and_months_tuples = self._year_months_to_years_and_months_tuples(
            year_months
        )

        if past_events_flag:
            default_events_q = Q(start_date__lte=get_past_event_cutoff())
        else:
            default_events_q = Q()  # Because we don't need to restrict

        if not years_and_months_tuples:
            # Covers case where no year_months, so no need to construct further queries
            return default_events_q

        # Build a Q where it's (Month X AND Year X) OR (Month Y AND Year Y), etc
        overall_date_q = None

        try:
            for year, month in years_and_months_tuples:
                date_q = Q(**{"start_date__year": year})
                date_q.add(Q(**{"start_date__month": month}), Q.AND)

                if overall_date_q is None:
                    overall_date_q = date_q
                else:
                    overall_date_q.add(date_q, Q.OR)
        except ValueError as e:
            logger.warning(
                "%s (years_and_months_tuples is %s)" % (e, years_and_months_tuples)
            )
            # Handles bad input and keeps the show on the road
            overall_date_q = Q()

        if past_events_flag:
            # Regardless of what's been specified in terms of specific dates, if
            # "past events" has been selected, we want to include all events
            # UP TO the past/future threshold date but _without_ de-scoping
            # whatever the other dates may have configured.
            all_past_events_q = Q(start_date__lte=get_past_event_cutoff())

            overall_date_q.add(all_past_events_q, Q.OR)  # NB: OR
        else:
            # We want specific months, but none in the past, so
            # ensure we don't include past events here (ie, same month as
            # selected dates, but before _today_)
            overall_date_q.add(
                Q(start_date__gte=get_past_event_cutoff()), Q.AND
            )  # NB: AND
        return overall_date_q

    def get_events(self, request):
        """Return filtered future events in chronological order"""

        countries = request.GET.getlist(COUNTRY_QUERYSTRING_KEY)
        date_params = request.GET.getlist(DATE_PARAMS_QUERYSTRING_KEY)
        topics = request.GET.getlist(TOPIC_QUERYSTRING_KEY)

        countries_q = Q(country__in=countries) if countries else Q()
        topics_q = Q(topics__topic__slug__in=topics) if topics else Q()

        # date_params need splitting to make them work, plus we need to see if
        # past events are also needed
        date_q = self._build_date_q(date_params)

        combined_q = Q()
        if countries_q:
            combined_q.add(countries_q, Q.AND)
        if date_q:
            combined_q.add(date_q, Q.AND)
        if topics_q:
            combined_q.add(topics_q, Q.AND)

        # Combined_q will always have something because it includes
        # the start_date__gte test
        events = get_combined_events(self, reverse=True, q_object=combined_q)

        events = paginate_resources(
            events,
            page_ref=request.GET.get(PAGINATION_QUERYSTRING_KEY),
            per_page=self.EVENTS_PER_PAGE,
        )

        return events

    def get_relevant_countries(self):
        # Relevant here means a country that a published Event is or was in
        raw_countries = (
            event.country
            for event in Event.published_objects.distinct("country").order_by("country")
            if event.country
        )

        return [
            {"code": country.code, "name": country.name} for country in raw_countries
        ]

    def get_relevant_dates(self):
        # Relevant here means a date for a published *future* event
        # TODO: would be good to cache this for short period of time
        raw_events = get_combined_events(self, start_date__gte=get_past_event_cutoff())
        return sorted([event.start_date for event in raw_events])

    def dates_to_unique_month_years(self, dates: List[datetime.date]):
        """From the given list of dates, generate another list of dates where the
        year-month combinations are unique and the `day` of each is set to the 1st.

        We do this because the filter-form.html template only uses Y and M when
        rendering the date options, so we must skip/merge dates that feature year-month
        pairs that _already_ appear in the list. If we don't, and if there is more than
        one Event for the same year-month, we end up with multiple Year-Months
        displayed in the filter options.

        NB: also note that the template slots in a special "all past dates" option.
        """
        return sorted(
            set([datetime.date(x.year, x.month, 1) for x in dates]), reverse=True
        )

    def get_filters(self):
        return {
            "countries": self.get_relevant_countries(),
            "dates": self.dates_to_unique_month_years(self.get_relevant_dates()),
            "topics": Topic.published_objects.order_by("title"),
        }


class Event(BasePage):
    resource_type = "event"
    parent_page_types = ["events.Events"]
    subpage_types = []
    template = "event.html"

    # Content fields
    description = RichTextField(
        blank=True,
        default="",
        features=RICH_TEXT_FEATURES_SIMPLE,
        help_text="Optional short text description, max. 400 characters",
        max_length=400,
    )
    start_date = DateField(default=datetime.date.today)
    end_date = DateField(blank=True, null=True)
    latitude = FloatField(blank=True, null=True)  # DEPRECATED
    longitude = FloatField(blank=True, null=True)  # DEPRECATED
    register_url = URLField("Register URL", blank=True, null=True)
    official_website = URLField("Official website", blank=True, default="")
    event_content = URLField(
        "Event content",
        blank=True,
        default="",
        help_text=(
            "Link to a page (in this site or elsewhere) "
            "with content about this event."
        ),
    )

    body = CustomStreamField(
        blank=True,
        null=True,
        help_text=(
            "Optional body content. Supports rich text, images, embed via URL, "
            "embed via HTML, and inline code snippets"
        ),
    )
    venue_name = CharField(max_length=100, blank=True, default="")  # DEPRECATED
    venue_url = URLField(
        "Venue URL", max_length=100, blank=True, default=""
    )  # DEPRECATED
    address_line_1 = CharField(max_length=100, blank=True, default="")  # DEPRECATED
    address_line_2 = CharField(max_length=100, blank=True, default="")  # DEPRECATED
    address_line_3 = CharField(max_length=100, blank=True, default="")  # DEPRECATED
    city = CharField(max_length=100, blank=True, default="")
    state = CharField(
        "State/Province/Region", max_length=100, blank=True, default=""
    )  # DEPRECATED
    zip_code = CharField(
        "Zip/Postal code", max_length=100, blank=True, default=""
    )  # DEPRECATED
    country = CountryField(blank=True, default="")
    agenda = StreamField(
        StreamBlock([("agenda_item", AgendaItemBlock())], required=False),
        blank=True,
        null=True,
        help_text="Optional list of agenda items for this event",
    )  # DEPRECATED
    speakers = StreamField(
        StreamBlock(
            [
                ("speaker", PageChooserBlock(target_model="people.Person")),
                ("external_speaker", ExternalSpeakerBlock()),
            ],
            required=False,
        ),
        blank=True,
        null=True,
        help_text="Optional list of speakers for this event",
    )  # DEPRECATED

    # Card fields
    card_title = CharField("Title", max_length=140, blank=True, default="")
    card_description = TextField("Description", max_length=400, blank=True, default="")
    card_image = ForeignKey(
        "mozimages.MozImage",
        null=True,
        blank=True,
        on_delete=SET_NULL,
        related_name="+",
        verbose_name="Image",
        help_text="An image in 16:9 aspect ratio",
    )
    card_image_3_2 = ForeignKey(
        "mozimages.MozImage",
        null=True,
        blank=True,
        on_delete=SET_NULL,
        related_name="+",
        verbose_name="Image",
        help_text="An image in 3:2 aspect ratio",
    )
    # Meta fields
    keywords = ClusterTaggableManager(through=EventTag, blank=True)

    # Content panels
    content_panels = BasePage.content_panels + [
        FieldPanel("description"),
        MultiFieldPanel(
            [
                FieldPanel("start_date"),
                FieldPanel("end_date"),
                FieldPanel("register_url"),
                FieldPanel("official_website"),
                FieldPanel("event_content"),
            ],
            heading="Event details",
            classname="collapsible",
            help_text=(
                "'Event content' should be used to link to a page (anywhere) "
                "which summarises the content of the event"
            ),
        ),
        StreamFieldPanel("body"),
        MultiFieldPanel(
            [FieldPanel("city"), FieldPanel("country")],
            heading="Event location",
            classname="collapsible",
            help_text=("The city and country are also shown on event cards"),
        ),
    ]

    # Card panels
    card_panels = [
        FieldPanel("card_title"),
        FieldPanel("card_description"),
        MultiFieldPanel(
            [ImageChooserPanel("card_image")],
            heading="16:9 Image",
            help_text=(
                "Image used for representing this page as a Card. "
                "Should be 16:9 aspect ratio. "
                "If not specified a fallback will be used. "
                "This image is also shown when sharing this page via social "
                "media unless a social image is specified."
            ),
        ),
        MultiFieldPanel(
            [ImageChooserPanel("card_image_3_2")],
            heading="3:2 Image",
            help_text=(
                "Image used for representing this page as a Card. "
                "Should be 3:2 aspect ratio. "
                "If not specified a fallback will be used. "
            ),
        ),
    ]

    # Meta panels
    meta_panels = [
        MultiFieldPanel(
            [InlinePanel("topics")],
            heading="Topics",
            help_text=(
                "These are the topic pages the event will appear on. The first topic "
                "in the list will be treated as the primary topic and will be shown "
                "in the page’s related content."
            ),
        ),
        MultiFieldPanel(
            [
                FieldPanel("seo_title"),
                FieldPanel("search_description"),
                ImageChooserPanel("social_image"),
                FieldPanel("keywords"),
            ],
            heading="SEO",
            help_text=(
                "Optional fields to override the default title and description "
                "for SEO purposes"
            ),
        ),
    ]

    # Settings panels
    settings_panels = BasePage.settings_panels + [FieldPanel("slug")]

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading="Content"),
            ObjectList(card_panels, heading="Card"),
            ObjectList(meta_panels, heading="Meta"),
            ObjectList(settings_panels, heading="Settings", classname="settings"),
        ]
    )

    @property
    def is_upcoming(self):
        """Returns whether an event is in the future."""
        return self.start_date >= get_past_event_cutoff()

    @property
    def primary_topic(self):
        """Return the first (primary) topic specified for the event."""
        article_topic = self.topics.first()
        return article_topic.topic if article_topic else None

    @property
    def month_group(self):
        return self.start_date.replace(day=1)

    @property
    def country_group(self):
        return (
            {"slug": self.country.code.lower(), "title": self.country.name}
            if self.country
            else {"slug": ""}
        )

    @property
    def event_dates(self):
        """Return a formatted string of the event start and end dates"""
        event_dates = self.start_date.strftime("%b %-d")
        if self.end_date and self.end_date != self.start_date:
            event_dates += " – "  # rather than &ndash; so we don't have to mark safe
            start_month = self.start_date.strftime("%m")
            if self.end_date.strftime("%m") == start_month:
                event_dates += self.end_date.strftime("%-d")
            else:
                event_dates += self.end_date.strftime("%b %-d")
        return event_dates

    @property
    def event_dates_full(self):
        """Return a formatted string of the event start and end dates,
        including the year"""
        return self.event_dates + self.start_date.strftime(", %Y")

    def has_speaker(self, person):
        for speaker in self.speakers:  # pylint: disable=not-an-iterable
            if speaker.block_type == "speaker" and str(speaker.value) == str(
                person.title
            ):
                return True
        return False

    @property
    def summary_meta(self):
        """Return a simple plaintext string that can be used
        as a standfirst"""

        summary = ""
        if self.event_dates:
            summary += self.event_dates
            if self.city or self.country:
                summary += " | "

        if self.city:
            summary += self.city
            if self.country:
                summary += ", "
        if self.country:
            summary += self.country.code
        return summary
