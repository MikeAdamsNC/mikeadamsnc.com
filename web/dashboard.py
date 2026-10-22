"""Numbers for Mike's private dashboard, straight from the analytics table."""
from .analytics import TABLE


def stats(recorder, days: int) -> dict:
    since = f"TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)"
    q = recorder.query
    def one(sql):
        rows = q(sql)
        return rows[0] if rows else {}
    return {
        "summary": one(f"""SELECT COUNTIF(kind='page_view') views,
              COUNT(DISTINCT IF(kind='page_view', CONCAT(SUBSTR(ts_eastern,1,10), visitor), NULL)) visitor_days,
              COUNTIF(kind='xray_open') xray, COUNTIF(kind='pitch_submit') pitches,
              COUNTIF(kind='vote') votes, COUNTIF(kind='comment') comments, COUNTIF(kind='sign_in') sign_ins,
              ROUND(AVG(IF(kind='page_view', server_ms, NULL)),1) avg_ms
            FROM `{TABLE}` WHERE ts >= {since}"""),
        "daily": q(f"""SELECT SUBSTR(ts_eastern,1,10) day, COUNTIF(kind='page_view') views,
              COUNT(DISTINCT IF(kind='page_view', visitor, NULL)) visitors
            FROM `{TABLE}` WHERE ts >= {since} GROUP BY day ORDER BY day"""),
        "pages": q(f"""SELECT path, COUNT(*) views FROM `{TABLE}` WHERE kind='page_view' AND ts >= {since}
            GROUP BY path ORDER BY views DESC LIMIT 15"""),
        "referrers": q(f"""SELECT IFNULL(referrer_host,'(direct or unknown)') source, COUNT(*) views FROM `{TABLE}`
            WHERE kind='page_view' AND ts >= {since} GROUP BY source ORDER BY views DESC LIMIT 10"""),
        "devices": q(f"""SELECT device, COUNT(*) views FROM `{TABLE}` WHERE kind='page_view' AND ts >= {since}
            GROUP BY device ORDER BY views DESC"""),
        "scroll": q(f"""SELECT CAST(deepest AS INT64) depth, COUNT(*) visits FROM (
              SELECT visitor, SUBSTR(ts_eastern,1,10) d, MAX(value) deepest FROM `{TABLE}`
              WHERE kind='scroll' AND path='/' AND ts >= {since} GROUP BY visitor, d)
            GROUP BY depth ORDER BY depth"""),
        "funnel": one(f"""SELECT COUNTIF(kind='page_view' AND path='/pitch') form_views,
              COUNTIF(kind='pitch_start') started, COUNTIF(kind='pitch_submit') sent
            FROM `{TABLE}` WHERE ts >= {since}"""),
        "experiments": q(f"""SELECT path, COUNT(*) views FROM `{TABLE}` WHERE kind='page_view' AND STARTS_WITH(path,'/lab/')
            AND ts >= {since} GROUP BY path ORDER BY views DESC"""),
        "outbound": q(f"""SELECT detail link, COUNT(*) clicks FROM `{TABLE}` WHERE kind='outbound' AND ts >= {since}
            GROUP BY link ORDER BY clicks DESC LIMIT 10"""),
    }
