from __future__ import annotations

import csv
import io

from app.core.config import settings
from app.schemas.analytics_catalog import AnalyticsCatalogRunRead


class AnalyticsExportLimitError(ValueError):
    pass


def analytics_result_csv(result: AnalyticsCatalogRunRead) -> bytes:
    """Serialize a deterministic analytics result to a UTF-8 BOM CSV.

    Money metrics are exported in major currency units (EGP pounds today), while
    the API/domain model continues to keep money in integer minor units.
    """
    if len(result.rows) > settings.analytics_export_max_rows:
        raise AnalyticsExportLimitError(
            f"تصدير التحليلات محدود بـ {settings.analytics_export_max_rows:,} صف. "
            "استخدم فترة أقصر أو فلاتر أضيق."
        )

    metric_columns = []
    seen: set[str] = set()
    for row in result.rows:
        for metric in row.metrics:
            if metric.key not in seen:
                seen.add(metric.key)
                metric_columns.append(metric)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "الاسم",
            "تفصيل",
            *[
                f"{metric.label} ({metric.currency})" if metric.currency else metric.label
                for metric in metric_columns
            ],
        ]
    )
    for row in result.rows:
        by_key = {metric.key: metric for metric in row.metrics}
        values: list[object] = [row.label, row.secondary_label or ""]
        for column in metric_columns:
            metric = by_key.get(column.key)
            if metric is None:
                values.append("")
                continue
            value = metric.value
            if metric.currency and isinstance(value, (int, float)):
                values.append(value / 100)
            else:
                values.append(value)
        writer.writerow(values)

    payload = ("\ufeff" + buffer.getvalue()).encode("utf-8")
    if len(payload) > settings.analytics_export_max_bytes:
        raise AnalyticsExportLimitError(
            f"حجم ملف التحليل تجاوز حد الأمان {settings.analytics_export_max_bytes // 1_000_000} MB. "
            "استخدم فترة أقصر أو فلاتر أضيق."
        )
    return payload
