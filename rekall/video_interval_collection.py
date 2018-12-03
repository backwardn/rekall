from operator import attrgetter
from rekall.interval_list import IntervalList
from rekall.temporal_predicates import *
from rekall.logical_predicates import *
from rekall.helpers import *
from rekall.merge_ops import *

class VideoIntervalCollection:
    """
    A VideoIntervalCollection is a wrapper around IntervalLists designed for
    videos. Logically, it contains a mapping from video ID's to IntervalLists.
    It exposes the same interface as an IntervalList.
    """

    # ============== CONSTRUCTORS ==============
    def __init__(self, video_ids_to_intervals):
        """
        video_ids_to_intervals is a dict mapping from video ID to either lists
        of (start, end, payload) tuples or an IntervalList.
        """
        self.intervals = {
            video_id: IntervalList(video_ids_to_intervals[video_id])
            for video_id in video_ids_to_intervals
        }

    def from_iterable(iterable, accessor, video_id_field, schema,
            with_payload=None):
        """
        Construct a VideoIntervalCollection from an iterable collection.

        @iterable is an iterable collection.
        @accessor takes items from @iterable and a field name and returns the
        value for that item; i.e. accessor(item, 'id') returns field 'id' of
        item.
        @video_id_field is the field name for the video ID that you group by.
        @schema is a dict mapping from "start", "end", and "payload" to field
        names for those items. For example, @schema might be:
        {
            "start": "min_frame",
            "end": "max_frame",
            "payload": "id"
        }
        @with_payload is for more complex payloads. If with_payload is None,
        then the payload just uses the field name from the schema. Otherwise,
        with_payload is a function that gets a payload from rows in the
        iterable.
        """
        video_ids_to_intervals = {}
        for row in iterable:
            new_tuple = (
                accessor(row, schema["start"]),
                accessor(row, schema["end"]),
                accessor(row, schema["payload"]) if with_payload is None
                else with_payload(row)
            )
            video_id = accessor(row, video_id_field)
            if accessor(row, video_id_field) in video_ids_to_intervals:
                video_ids_to_intervals[video_id].append(new_tuple)
            else:
                video_ids_to_intervals[video_id] = [new_tuple]

        return VideoIntervalCollection(video_ids_to_intervals)

    def spark_accessor(row, field):
            return row[field]

    def from_spark_df(dataframe, video_id_field="video_id", schema=None,
            with_payload=None):
        """
        Constructor from a Spark dataframe.
        By default, the schema is 
        {
            "start": "min_frame",
            "end": "max_frame",
            "payload": "id"
        }
        """
        if schema is None:
            schema = { "start": "min_frame",
                    "end": "max_frame",
                    "payload": "id" }

        dfmaterialized = dataframe.collect()

        return VideoIntervalCollection.from_iterable(dfmaterialized,
                VideoIntervalCollection.spark_accessor, video_id_field, schema,
                with_payload=with_payload)

    def django_accessor(row, field):
        return attrgetter(field)(row)

    def from_django_qs(qs, video_id_field="video_id", schema=None,
            with_payload=None):
        """
        Constructor for a Django queryset.
        By default, the schema is 
        {
            "start": "min_frame",
            "end": "max_frame",
            "payload": "id"
        }
        """
        if schema is None:
            schema = { "start": "min_frame",
                    "end": "max_frame",
                    "payload": "id" }

        return VideoIntervalCollection.from_iterable(qs,
                VideoIntervalCollection.django_accessor, video_id_field,
                schema, with_payload=with_payload)

    def _remove_empty_intervallists(intervals):
        return { video_id: intervals[video_id]
                for video_id in intervals
                if intervals[video_id].size() > 0 }

    # ============== GETTERS ==============
    def get_intervallist(self, video_id):
        return self.intervals[video_id]
    def get_allintervals(self):
        return self.intervals

    # ============== FUNCTIONS THAT MODIFY SELF ==============
    def coalesce(self, payload_merge_op=payload_first):
        """ See IntervalList#coalesce for details. """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].coalesce(
                        payload_merge_op)
                    for video_id in list(self.intervals.keys()) }))

    def dilate(self, window):
        """ See IntervalList#dilate for details. """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].dilate(window)
                    for video_id in list(self.intervals.keys()) }))

    def filter(self, fn):
        """ See IntervalList#filter for details. """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].filter(fn)
                    for video_id in list(self.intervals.keys()) }))

    def filter_length(self, min_length=0, max_length=INFTY):
        """ See IntervalList#filter_length for details. """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].filter_length(
                        min_length, max_length)
                    for video_id in list(self.intervals.keys()) }))

    # ============== GENERAL LIST OPERATIONS ==============
    def map(self, map_fn):
        """ See IntervalList#map for details. """
        return VideoIntervalCollection({
            video_id: self.intervals[video_id].map(map_fn)
            for video_id in list(self.intervals.keys()) })

    def join(self, other, merge_op, predicate):
        """
        Inner join on video ID between self and other, and then join the
        IntervalList's of self and other for the video ID.
        """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].join(
                        other.intervals[video_id],
                        merge_op,
                        predicate)
                    for video_id in list(self.intervals.keys())
                    if video_id in other.intervals }))

    def fold(self, fold_fn, init_acc):
        """
        Returns a dict from video ID to the fold result from applying the
        fold function to each IntervalList. See IntervalList#fold for details.
        """
        return { video_id: self.intervals[video_id].fold(fold_fn, init_acc)
                for video_id in list(self.intervals.keys()) }

    def fold_list(self, fold_fn, init_acc):
        """
        Assumes that the accumulator is a list of Intervals; applies the fold
        function to each IntervalList and returns a Video IntervalCollection.
        """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].fold_list(
                        fold_fn, init_acc)
                    for video_id in list(self.intervals.keys()) }))

    # ============== FUNCTIONS THAT JOIN WITH ANOTHER COLLECTION ==============
    
    def set_union(self, other):
        """ Full outer join on video ID's, union between self and other. """
        video_ids = set(self.intervals.keys()).union(
            set(other.intervals.keys()))

        return VideoIntervalCollection({
            video_id : (
                self.intervals[video_id].set_union(other.intervals[video_id])
                if (video_id in list(self.intervals.keys())
                    and video_id in other.intervals)
                else (self.intervals[video_id]
                    if video_id in list(self.intervals.keys())
                    else other.intervals[video_id])
            )
            for video_id in video_ids })

    def filter_against(self, other, predicate=true_pred(arity=2)):
        """
        Inner join on video ID's, computing IntervalList#filter_against.
        """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id : self.intervals[video_id].filter_against(
                        other.intervals[video_id], predicate)
                    for video_id in list(self.intervals.keys())
                    if video_id in list(other.intervals.keys()) }))

    def minus(self, other, recursive_diff = True, predicate = true_pred(arity=2),
        payload_merge_op=payload_first):
        """ Left outer join on video ID's, computing IntervalList#minus. """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id : (
                        self.intervals[video_id].minus(
                            other.intervals[video_id], predicate)
                        if video_id in other.intervals.keys()
                        else self.intervals[video_id]
                    )
                    for video_id in list(self.intervals.keys()) }))

    def overlaps(self, other, predicate = true_pred(arity=2), payload_merge_op =
        payload_first):
        """ Inner join on video ID's, computing IntervalList#overlaps. """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].overlaps(
                        other.intervals[video_id], predicate = predicate,
                        payload_merge_op = payload_merge_op)
                    for video_id in list(self.intervals.keys())
                    if video_id in list(other.intervals.keys()) }))

    def merge(self, other, predicate = true_pred(arity=2), payload_merge_op =
        payload_first):
        """ Inner join on video ID's, computing IntervalList#merge. """
        return VideoIntervalCollection(
                VideoIntervalCollection._remove_empty_intervallists({
                    video_id: self.intervals[video_id].merge(
                        other.intervals[video_id], predicate = predicate,
                        payload_merge_op = payload_merge_op)
                    for video_id in list(self.intervals.keys())
                    if video_id in list(other.intervals.keys()) }))

