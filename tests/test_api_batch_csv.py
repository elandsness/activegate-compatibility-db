import csv
import io

from src.api.app import app

REQUIRED_HEADERS = [
    "current_activegate_version",
    "target_activegate_version",
    "managed_cluster_version",
    "os_family",
    "os_version",
    "extensions",
]


def test_check_template_csv_download():
    client = app.test_client()

    response = client.get("/api/check/template")

    assert response.status_code == 200
    assert "text/csv" in response.content_type
    assert "attachment;" in response.headers.get("Content-Disposition", "")

    content = response.data.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(content)))

    assert rows
    assert rows[0]["current_activegate_version"] == "1.330"
    assert rows[0]["target_activegate_version"] == "1.335"


def test_batch_csv_check_returns_augmented_rows_with_row_errors():
    client = app.test_client()

    input_csv = "\n".join(
        [
            ",".join(REQUIRED_HEADERS),
            '1.330,1.335,1.335,linux,8,"{""custom-ext"":""2.0.0""}"',
            '1.331,,1.335,linux,8,"{""custom-ext"":""2.0.0""}"',
            '1.332,1.335,1.335,linux,8,"{bad-json}"',
        ]
    )

    response = client.post(
        "/api/check/batch-csv",
        data={"file": (io.BytesIO(input_csv.encode("utf-8")), "batch.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "text/csv" in response.content_type

    output_csv = response.data.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(output_csv)))

    assert len(rows) == 3

    for header in [
        "compatibility_status",
        "compatibility_confidence",
        "compatibility_issues",
        "compatibility_warnings",
        "compatibility_recommendations",
        "row_error",
    ]:
        assert header in rows[0]

    assert rows[0]["compatibility_status"]
    assert rows[0]["row_error"] == ""

    assert rows[1]["row_error"]
    assert "target_activegate_version" in rows[1]["row_error"]

    assert rows[2]["row_error"]
    assert "Invalid extensions JSON" in rows[2]["row_error"]


def test_batch_csv_requires_expected_headers():
    client = app.test_client()

    input_csv = "current_activegate_version,target_activegate_version\n1.330,1.335\n"

    response = client.post(
        "/api/check/batch-csv",
        data={"file": (io.BytesIO(input_csv.encode("utf-8")), "batch.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400

    payload = response.get_json()
    assert payload["error"] == "Missing required CSV headers"
    assert "managed_cluster_version" in payload["missing_headers"]
