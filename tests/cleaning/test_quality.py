from app.cleaning.quality import problem_columns, quality_issues


def test_quality_issues__none_for_a_clean_record() -> None:
    fields = {
        "publication_date": "2020/05/",
        "author_names": "A|B",
        "author_ids": "x:1|x:2",
        "publication_type": "Journal article",
    }

    assert quality_issues(fields) == []


def test_quality_issues__all_problems_in_check_order() -> None:
    fields = {
        "publication_date": "May 2020",
        "author_names": "A",
        "author_ids": "x:[1;2]",
        "publication_type": "JOUR",
    }

    assert quality_issues(fields) == [
        "Unparsed dates",
        "Misaligned authors",
        "Unmapped pub. types",
    ]


def test_quality_issues__missing_fields_are_no_problem() -> None:
    assert quality_issues({}) == []


def test_problem_columns__data_quality_plus_columns_of_found_problems() -> None:
    counts = {"Unparsed dates": 0, "Misaligned authors": 3}

    assert problem_columns(counts) == ["data_quality", "author_names", "author_ids"]


def test_problem_columns__every_problem_found() -> None:
    counts = {
        "Unparsed dates": 1,
        "Misaligned authors": 1,
        "Unmapped pub. types": 1,
    }

    assert problem_columns(counts) == [
        "data_quality",
        "publication_date",
        "author_names",
        "author_ids",
        "publication_type",
    ]
