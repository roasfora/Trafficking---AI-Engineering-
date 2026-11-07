"""Mini-workflow: pedido (request.json) + dados (sample_data.json) -> relatorio JSON.

O relatorio e calculado em codigo (sem LLM), com a mesma regra do exemplo
cr-drops-goncalo.vitor.json:
  CR drop >= 25%  E  >= 30 conversoes no bloco recente  E  p < 0.05 (z-test, 1 lado).

Uso: python run_report.py [request.json] [sample_data.json] [saida.json]
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from math import sqrt
from statistics import NormalDist

MIN_DROP, MIN_CONV, ALPHA = 0.25, 30, 0.05


def z_test(conv_prev, den_prev, conv_recent, den_recent):
    """Teste z de duas proporcoes (pooled), de um lado: queda do CR."""
    p_prev, p_recent = conv_prev / den_prev, conv_recent / den_recent
    pooled = (conv_prev + conv_recent) / (den_prev + den_recent)
    z = (p_recent - p_prev) / sqrt(pooled * (1 - pooled) * (1 / den_prev + 1 / den_recent))
    return z, NormalDist().cdf(z)


def analyse_row(row):
    """Devolve o finding se a linha cumprir a regra, senao None."""
    cr_prev = row["conv_prev"] / row["den_prev"]
    cr_recent = row["conv_recent"] / row["den_recent"]
    drop = (cr_prev - cr_recent) / cr_prev
    z, p = z_test(row["conv_prev"], row["den_prev"], row["conv_recent"], row["den_recent"])
    if drop < MIN_DROP or row["conv_recent"] < MIN_CONV or p >= ALPHA:
        return None
    confidence = "very high (>99.9%)" if p < 0.001 else f"high (>{(1 - ALPHA) * 100:.0f}%)"
    finding = {
        "badge": "b-watch",
        "title": row["campaign"],
        "summary": f"{row['offer']} — CR (conv/{row['denominator']}): "
                   f"{cr_prev:.2%} → {cr_recent:.2%} (↓{drop:.0%}), confidence {confidence}",
        "kpis": [
            {"label": "CR drop", "value": f"↓{drop:.0%}"},
            {"label": "CR prev", "value": f"{cr_prev:.2%}"},
            {"label": "CR recent", "value": f"{cr_recent:.2%}"},
            {"label": "Conv recent", "value": str(row["conv_recent"])},
            {"label": "Conv prev", "value": str(row["conv_prev"])},
            {"label": "Denom", "value": row["denominator"]},
            {"label": "p-value", "value": f"{p:.4f}"},
        ],
        "body": f'Offer "{row["offer"]}". Two-proportion z-test z={z:.2f}, p={p:.4f}.',
        "dimension": "offer",
    }
    if row["geo"]:
        finding["geo"] = row["geo"]
    return finding, drop


def validate(report):
    """Mesmas regras do prompt do Billy: geos == geo dos findings, sem duplicados."""
    found = {f["geo"] for s in report["sections"] if s["type"] == "finding_list"
             for f in s["findings"] if "geo" in f}
    assert sorted(report["geos"]) == sorted(found), "geos != geo dos findings"
    assert len(report["geos"]) == len(set(report["geos"])), "geos duplicados"
    assert report["status"] in {"accepted", "pending", "ok", "error"}
    assert report["severity"] in {"blue", "red", "amber", "green"}


def build_report(request, data):
    results = [r for r in (analyse_row(row) for row in data["rows"]) if r]
    results.sort(key=lambda r: (r[0].get("geo", "ZZ"), -r[1]))   # agrupa por geo
    findings = [f for f, _ in results]
    end = datetime.fromisoformat(data["as_of"])
    start = end - timedelta(days=request["window_days"] - 1)
    report = {
        "version": "1",
        "reportType": request["analysis"],
        "subject": {"type": "workspace", "id": request["staff_id"], "label": request["staff_label"]},
        "window": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "currency": "USD",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": "ok",
        "severity": "red" if findings else "green",
        "headline": f"{len(findings)} significant CR drops for {request['staff_label']} "
                    f"(from {len(data['rows'])} campaign×offer pairs)",
        "count_label": f"{len(findings)} CR drops",
        "notes": f"Analysis over a {request['window_days']}d window "
                 f"(last {request['window_days'] // 2}d vs prior {request['window_days'] // 2}d). "
                 "Synthetic demo data.",
        "geos": sorted({f["geo"] for f in findings if "geo" in f}),
        "sections": [
            {"type": "finding_list",
             "rule": f"Flag when CR drop ≥{MIN_DROP:.0%} AND ≥{MIN_CONV} conversions in recent block "
                     f"AND statistically significant (two-proportion z-test, α={ALPHA}).",
             "findings": findings},
            {"type": "bar_chart", "title": "CR drop % by campaign (recent vs previous)",
             "labels": [f["title"][:40] for f in findings],
             "data": [round(d * 100) for _, d in results], "unit": "%"},
        ],
    }
    validate(report)
    return report


if __name__ == "__main__":
    req_path = sys.argv[1] if len(sys.argv) > 1 else "request.json"
    data_path = sys.argv[2] if len(sys.argv) > 2 else "sample_data.json"
    out_path = sys.argv[3] if len(sys.argv) > 3 else "report_output.json"
    with open(req_path) as f, open(data_path) as g:
        report = build_report(json.load(f), json.load(g))
    with open(out_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"{report['headline']} -> {out_path}")
