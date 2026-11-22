"""The Watch list's rule (sandbox research): every item and its history worked out from the looks, in order. Pure: no
database and no network. A weakness becomes an item at the first look that finds it with no fixed version named."""
from __future__ import annotations

from app.changewatch import watchlist as w

OPEN = [{"introduced": "0", "fixed": None, "last_affected": None}]
FIXED = [{"introduced": "0", "fixed": "1.2.5", "last_affected": None}]
FIXED_LATER = [{"introduced": "0", "fixed": "1.3.0", "last_affected": None}]
LAST = [{"introduced": "0", "fixed": None, "last_affected": "1.2.4"}]


def look(number: int, found: list[dict] | None = None, *, withdrawn: list[dict] | None = None, asked=("lib",), cut: bool = False) -> dict:
    return {"number": number, "at": f"2026-11-{number:02d}T09:00:00Z", "cut": cut, "asked": list(asked), "found": found or [],
            "withdrawn": withdrawn or []}


def found(ranges: list[dict], id_: str = "CVE-2026-0001", library: str = "lib", aliases=()) -> dict:
    return {"id": id_, "aliases": list(aliases), "library": library, "ranges": w.facts_of(ranges)}


def kinds(item: dict) -> list[str]:
    return [e["kind"] for e in item["events"]]


def test_a_weakness_with_no_fixed_version_named_becomes_an_item_at_the_look_that_finds_it():
    [item] = w.derive([look(1, [found(OPEN)])])
    assert (item["key"], item["id"], item["library"], item["state"]) == ("CVE-2026-0001~lib", "CVE-2026-0001", "lib", "no_fix")
    assert item["first"] == {"look": 1, "at": "2026-11-01T09:00:00Z"} and kinds(item) == ["seen_no_fix"]
    assert item["new"] is True and item["quiet"] == 0 and item["ends"] == {"fixed": [], "last_affected": []}


def test_one_that_names_an_end_from_the_first_time_it_is_seen_is_not_for_this_list():
    assert w.derive([look(1, [found(FIXED)])]) == []
    assert w.derive([look(1, [found(LAST)])]) == []          # a last affected version is an end too
    assert w.derive([look(1, [found([])])]) == []            # single versions only, or nothing read: no open range


def test_looks_that_change_nothing_add_no_event_and_the_new_tag_goes():
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found(OPEN)]), look(3, [found(OPEN)])])
    assert kinds(item) == ["seen_no_fix"] and item["quiet"] == 2 and item["new"] is False
    assert item["last"] == {"look": 3, "at": "2026-11-03T09:00:00Z"}


def test_the_day_a_fixed_version_is_named_is_one_event_and_the_item_is_new_again():
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found(OPEN)]), look(3, [found(FIXED)])])
    assert item["state"] == "fix_published" and item["ends"] == {"fixed": ["1.2.5"], "last_affected": []}
    assert kinds(item) == ["seen_no_fix", "fix_published"] and item["events"][-1] == {
        "look": 3, "at": "2026-11-03T09:00:00Z", "kind": "fix_published", "ends": {"fixed": ["1.2.5"], "last_affected": []}}
    assert item["new"] is True and item["quiet"] == 1
    # a last affected version named where there was no end reads as a fix too (every version after it)
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found(LAST)])])
    assert item["state"] == "fix_published" and item["ends"] == {"fixed": [], "last_affected": ["1.2.4"]}


def test_every_other_change_is_recorded_as_what_it_is():
    looks = [look(1, [found(OPEN)]), look(2, [found(FIXED)]), look(3, [found(FIXED_LATER)]), look(4, [found(OPEN)]),
             look(5, [found([{"introduced": "1.0.0", "fixed": None, "last_affected": None}])])]
    [item] = w.derive(looks)
    assert kinds(item) == ["seen_no_fix", "fix_published", "fix_changed", "fix_no_longer_named", "versions_changed"]
    changed = item["events"][2]
    assert changed["before"] == {"fixed": ["1.2.5"], "last_affected": []} and changed["ends"] == {"fixed": ["1.3.0"], "last_affected": []}
    assert item["events"][3]["before"] == {"fixed": ["1.3.0"], "last_affected": []} and item["state"] == "no_fix"


def test_a_record_with_one_line_fixed_and_another_still_open_stays_no_fix_yet():
    both = [{"introduced": "1.0.0", "fixed": "1.2.5", "last_affected": None}, {"introduced": "2.0.0", "fixed": None, "last_affected": None}]
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found(both)])])
    assert item["state"] == "no_fix" and item["ends"]["fixed"] == ["1.2.5"] and kinds(item) == ["seen_no_fix", "fix_changed"]


def test_withdrawn_is_said_once_and_a_record_that_comes_back_says_so():
    gone = [{"library": "lib", "ids": ["GHSA-AAAA-BBBB-CCCC", "CVE-2026-0001"]}]
    looks = [look(1, [found(OPEN)]), look(2, withdrawn=gone), look(3, withdrawn=gone), look(4, [found(OPEN)])]
    assert [i["state"] for i in (w.derive(looks[:2])[0], w.derive(looks[:3])[0], w.derive(looks)[0])] == ["withdrawn", "withdrawn", "no_fix"]
    assert kinds(w.derive(looks[:3])[0]) == ["seen_no_fix", "withdrawn"]
    assert kinds(w.derive(looks)[0]) == ["seen_no_fix", "withdrawn", "back"]
    # a withdrawn record that was never an item is nothing to this list
    assert w.derive([look(1, withdrawn=gone)]) == []


def test_missing_from_an_answer_counts_only_where_the_look_asked_and_kept_everything():
    first = look(1, [found(OPEN)])
    assert w.derive([first, look(2)])[0]["state"] == "gone" and kinds(w.derive([first, look(2)])[0]) == ["seen_no_fix", "gone"]
    assert w.derive([first, look(2, cut=True)])[0]["state"] == "no_fix"           # a look that was cut short may not list it
    assert w.derive([first, look(2, asked=("other",))])[0]["state"] == "no_fix"   # its library was not asked about
    back = w.derive([first, look(2), look(3, [found(OPEN)])])[0]
    assert back["state"] == "no_fix" and kinds(back) == ["seen_no_fix", "gone", "back"]


def test_one_weakness_under_two_ids_is_one_item_and_two_libraries_are_two():
    looks = [look(1, [found(OPEN, "GHSA-AAAA-BBBB-CCCC", aliases=["CVE-2026-0001"])]),
             look(2, [found(FIXED, "CVE-2026-0001", aliases=["GHSA-AAAA-BBBB-CCCC"])])]
    [item] = w.derive(looks)
    assert item["key"] == "GHSA-AAAA-BBBB-CCCC~lib" and item["state"] == "fix_published"
    assert item["ids"] == ["GHSA-AAAA-BBBB-CCCC", "CVE-2026-0001"]
    two = w.derive([look(1, [found(OPEN), found(OPEN, library="other")], asked=("lib", "other"))])
    assert [i["key"] for i in two] == ["CVE-2026-0001~lib", "CVE-2026-0001~other"]


def test_the_rule_reads_only_its_argument_and_gives_the_same_answer_twice():
    looks = [look(1, [found(OPEN)]), look(2, [found(FIXED)])]
    import copy
    before = copy.deepcopy(looks)
    assert w.derive(looks) == w.derive(looks) and looks == before


# ---------------------------------------------------------------- "Fix published" needs the source to NAME an end

def test_a_record_that_stops_giving_version_ranges_names_no_fix_and_the_item_stays_where_it_stood():
    """The separate review of 22 November 2026: a record that no longer gave any ranges moved its item to Fix published,
    with "the source names a fixed version: none"."""
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found([])])])
    assert item["state"] == "no_fix" and kinds(item) == ["seen_no_fix", "versions_changed"]
    assert item["ends"] == {"fixed": [], "last_affected": []} and item["ranges"] == w.facts_of(OPEN)       # the ranges that were last given
    # looked at again with still no ranges: nothing new is said
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found([])]), look(3, [found([])])])
    assert kinds(item) == ["seen_no_fix", "versions_changed"] and item["quiet"] == 1
    # the day the source names a fixed version is still the day the item moves
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found([])]), look(3, [found(FIXED)])])
    assert item["state"] == "fix_published" and kinds(item) == ["seen_no_fix", "versions_changed", "fix_published"]
    assert item["events"][-1]["ends"] == {"fixed": ["1.2.5"], "last_affected": []}


def test_a_fix_that_was_named_is_not_taken_back_because_the_ranges_are_no_longer_given():
    [item] = w.derive([look(1, [found(OPEN)]), look(2, [found(FIXED)]), look(3, [found([])])])
    assert item["state"] == "fix_published" and item["ends"] == {"fixed": ["1.2.5"], "last_affected": []}  # never "Fixed in none"
    assert kinds(item) == ["seen_no_fix", "fix_published", "versions_changed"]


def test_a_record_with_no_ranges_is_not_put_on_the_list_for_that():
    assert w.derive([look(1, [found([])])]) == []


def test_fix_published_always_names_an_end_over_many_made_up_histories_in_both_writings_of_the_rule():
    """Whatever the source does from look to look: an item reads Fix published only with a fixed version or a last
    affected version named, and every "fix published" entry of a history names one."""
    import random

    from evidence import watchlist as check
    ranges = (OPEN, FIXED, FIXED_LATER, LAST, [], [{"introduced": "1.0.0", "fixed": "1.2.5", "last_affected": None},
                                                    {"introduced": "2.0.0", "fixed": None, "last_affected": None}])
    rng = random.Random(20261122)
    seen = 0
    for _ in range(2000):
        looks = [look(n, [found(rng.choice(ranges))] if rng.random() < 0.85 else []) for n in range(1, rng.randint(2, 8))]
        for items in (w.derive(looks), check.work_out(looks)):
            for item in items:
                if item["state"] == "fix_published":
                    assert item["ends"]["fixed"] or item["ends"]["last_affected"], looks
                    seen += 1
                for event in item["events"]:
                    if event["kind"] == "fix_published":
                        assert event["ends"]["fixed"] or event["ends"]["last_affected"], looks
    assert seen > 500
