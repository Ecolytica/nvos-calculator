import io

import pytest

import app


SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"


def _xls(rows):
    xml_rows = []
    for row in rows:
        cells = []
        for index, value in sorted(row.items()):
            cells.append(
                f'<Cell ss:Index="{index}"><Data ss:Type="String">{value}</Data></Cell>'
            )
        xml_rows.append(f"<Row>{''.join(cells)}</Row>")
    content = (
        '<?xml version="1.0"?>'
        f'<Workbook xmlns="{SS_NS}" xmlns:ss="{SS_NS}">'
        '<Worksheet ss:Name="Page1"><Table>'
        f"{''.join(xml_rows)}"
        "</Table></Worksheet></Workbook>"
    )
    return io.BytesIO(content.encode("utf-8"))


def test_parses_object_format():
    uploaded = _xls([
        {
            2: (
                "Нормативы выбросов загрязняющих веществ от стационарных ИЗАВ "
                "в атмосферный воздух  по объекту ОНВ."
            )
        },
        {1: "1", 2: "0155  Натрия карбонат", 6: "0,000036"},
        {1: "2", 2: "0301  Азота диоксид", 6: "8.369627"},
    ])

    result = app.parse_emissions_xls(uploaded)

    assert result.success
    assert result.dataframe["Код вещества"].tolist() == ["0155", "0301"]
    assert result.dataframe["Валовый выброс, т/год"].tolist() == pytest.approx(
        [0.000036, 8.369627]
    )


def test_parses_source_format_from_substance_totals_only():
    title = (
        "Нормативы выбросов загрязняющих веществ в атмосферный воздух "
        "по конкретным стационарным источникам выбросов и загрязняющим веществам"
    )
    uploaded = _xls([
        {4: title},
        {1: "Наименование и код загрязняющего вещества:", 5: "0155 Натрия карбонат"},
        {1: "1", 3: "0006", 5: "0.000020", 6: "ПДВ"},
        {2: "Всего по ЗВ", 5: "3,60e-05"},
        # Повторный заголовок страницы не должен создавать запись.
        {4: title},
        {1: "Наименование и код загрязняющего вещества:", 5: "0301 Азота диоксид"},
        {1: "2", 3: "0008", 5: "0.060800", 6: "ПДВ"},
        {1: "3", 3: "0009", 5: "5.913600", 6: "ПДВ"},
        {2: "Всего по ЗВ", 5: "8.369627"},
    ])

    result = app.parse_emissions_xls(uploaded)

    assert result.success
    assert result.dataframe["Код вещества"].tolist() == ["0155", "0301"]
    assert result.dataframe["Валовый выброс, т/год"].tolist() == pytest.approx(
        [0.000036, 8.369627]
    )
    assert len(result.dataframe) == 2


def test_rejects_unknown_spreadsheetml_format():
    result = app.parse_emissions_xls(_xls([{1: "Другая таблица"}]))

    assert not result.success
    assert result.error_category == "unsupported_format"
    assert "Не удалось определить вид таблицы" in result.user_message