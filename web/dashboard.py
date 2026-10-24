"""Numbers for Mike's private dashboard, straight from the analytics table."""
from .analytics import TABLE


# Each visitor-day is sorted into one group, first match wins:
#   bot       its browser said it was a bot (Googlebot, ClaudeBot, curl...)
#   person    it did something only a person does: touched, scrolled, clicked, typed,
#             moved the mouse ("here"), voted, chatted, pitched or commented
#   scanner   it asked for pages that don't exist (/.env, /.git/config, /wp-login.php...)
#   unseen    it loaded pages and never touched them: quiet scripts, plus a few people
#             who left within a second
GROUPS = ["person", "unseen", "scanner", "bot"]


def stats(recorder, days: int) -> dict:
    since = f"TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)"
    sorted_days = f"""WITH ev AS (SELECT *, CONCAT(SUBSTR(ts_eastern,1,10), visitor) vd FROM `{TABLE}` WHERE ts >= {since}),
      grp AS (SELECT vd, CASE
          WHEN LOGICAL_OR(kind='page_view' AND IFNULL(detail,'')='bot') THEN 'bot'
          WHEN LOGICAL_OR(kind!='page_view') THEN 'person'
          WHEN LOGICAL_OR(kind='page_view' AND status=404) THEN 'scanner'
          ELSE 'unseen' END g FROM ev GROUP BY vd),
      people AS (SELECT ev.* FROM ev JOIN grp USING (vd) WHERE g='person')"""

    def q(sql):
        return recorder.query(f"{sorted_days}\n{sql}")

    def one(sql):
        rows = q(sql)
        return rows[0] if rows else {}
    return {
        "groups": {r["g"]: r for r in q("""SELECT g, COUNTIF(kind='page_view') views, COUNT(DISTINCT vd) visitors
            FROM ev JOIN grp USING (vd) GROUP BY g""")},
        "summary": one("""SELECT COUNTIF(kind='page_view') views,
              COUNT(DISTINCT IF(kind='page_view', vd, NULL)) visitor_days,
              COUNTIF(kind='xray_open') xray, COUNTIF(kind='pitch_submit') pitches,
              COUNTIF(kind='vote') votes, COUNTIF(kind='comment') comments, COUNTIF(kind='sign_in') sign_ins,
              ROUND(AVG(IF(kind='page_view', server_ms, NULL)),1) avg_ms
            FROM people"""),
        "daily": q("""SELECT SUBSTR(ts_eastern,1,10) day, COUNTIF(kind='page_view') views,
              COUNT(DISTINCT IF(kind='page_view', visitor, NULL)) visitors
            FROM people GROUP BY day ORDER BY day"""),
        "pages": q("""SELECT path, COUNT(*) views FROM people WHERE kind='page_view'
            GROUP BY path ORDER BY views DESC LIMIT 15"""),
        "referrers": q("""SELECT IFNULL(referrer_host,'(direct or unknown)') source, COUNT(*) views FROM people
            WHERE kind='page_view' GROUP BY source ORDER BY views DESC LIMIT 10"""),
        "devices": q("""SELECT device, COUNT(*) views FROM people WHERE kind='page_view'
            GROUP BY device ORDER BY views DESC"""),
        "scroll": q("""SELECT CAST(deepest AS INT64) depth, COUNT(*) visits FROM (
              SELECT vd, MAX(value) deepest FROM people WHERE kind='scroll' AND path='/' GROUP BY vd)
            GROUP BY depth ORDER BY depth"""),
        "funnel": one("""SELECT COUNTIF(kind='page_view' AND path='/pitch') form_views,
              COUNTIF(kind='pitch_start') started, COUNTIF(kind='pitch_submit') sent
            FROM people"""),
        "experiments": q("""SELECT path, COUNT(*) views FROM people WHERE kind='page_view' AND STARTS_WITH(path,'/lab/')
            GROUP BY path ORDER BY views DESC"""),
        "scanned": q("""SELECT path, COUNT(*) hits FROM ev WHERE kind='page_view' AND status=404
            GROUP BY path ORDER BY hits DESC LIMIT 8"""),
        "outbound": q("""SELECT detail link, COUNT(*) clicks FROM people WHERE kind='outbound'
            GROUP BY link ORDER BY clicks DESC LIMIT 10"""),
    }
