# Script ดึงข้อมูล post fb
import os
import requests
import psycopg2
import json
from dotenv import load_dotenv

load_dotenv()

PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")
FB_PAGE_ACCESS_TOKENS = os.getenv("FB_PAGE_ACCESS_TOKENS").split(',')
FB_PAGE_IDS = os.getenv("FB_PAGE_IDS").split(',')

conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD
)
cur = conn.cursor()

try:
    cur.execute("SET search_path TO public;")
except Exception as e:
    print(f"Warning: cannot set search_path: {e}")

for page_id, token in zip(FB_PAGE_IDS, FB_PAGE_ACCESS_TOKENS):
    print(f"\nFetching posts for page_id: {page_id}")
    posts_url = (
        f"https://graph.facebook.com/v22.0/{page_id}/posts?"
        "fields=id,created_time,message"
        f"&limit=100&access_token={token}"
    )
    posts_resp = requests.get(posts_url)
    posts_json = posts_resp.json()
    print(f"API response: {posts_json}")
    posts = posts_json.get("data", [])
    print(f"Found {len(posts)} posts for page_id {page_id}")
    for post in posts:
        print(f"Inserting post id: {post.get('id')}, message: {post.get('message')}")
        cur.execute(
            """
            INSERT INTO facebook_posts (
                id, page_id, message, created_time, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, now(), now())
            ON CONFLICT (id) DO UPDATE SET
                message=EXCLUDED.message,
                updated_at=now()
            """,
            (
                post.get("id"),
                page_id,
                post.get("message"),
                post.get("created_time")
            )
        )

        # ดึง attachments ของแต่ละโพสต์
        att_url = f"https://graph.facebook.com/v22.0/{post.get('id')}/attachments?access_token={token}"
        att_resp = requests.get(att_url)
        att_json = att_resp.json()
        attachments = att_json.get("data", [])
        print(f"  Attachments found: {len(attachments)}")
        for att in attachments:
            media = att.get("media", {})
            print(f"    Attachment type: {att.get('type')}, media_url: {media.get('source') or media.get('image', {}).get('src')}")
            cur.execute(
                """
                INSERT INTO facebook_post_attachments (
                    post_id, type, media_url, thumbnail_url, description, title, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (post_id, type, media_url) DO UPDATE SET
                    thumbnail_url=EXCLUDED.thumbnail_url,
                    description=EXCLUDED.description,
                    title=EXCLUDED.title,
                    created_at=now()
                """,
                (
                    post.get("id"),
                    att.get("type"),
                    media.get("source") or media.get("image", {}).get("src"),
                    media.get("image", {}).get("src"),
                    att.get("description"),
                    att.get("title")
                )
            )

        # ดึง insights ของแต่ละโพสต์ (v23.0, skip metric ที่ error)
        metrics = [
            "post_impressions",
            "post_impressions_unique",
            "post_clicks",
            "post_reactions_by_type_total",
            "post_video_views",
            "post_video_avg_time_watched",
            "post_video_complete_views_organic"
        ]
        for metric in metrics:
            insights_url = f"https://graph.facebook.com/v23.0/{post.get('id')}/insights?metric={metric}&access_token={token}"
            insights_resp = requests.get(insights_url)
            insights_json = insights_resp.json()
            if 'error' in insights_json:
                print(f"  Skip metric {metric}: {insights_json['error']['message']}")
                continue
            insights = insights_json.get("data", [])
            for insight in insights:
                metric_name = insight.get("name")
                value_obj = insight.get("values", [{}])[0].get("value", 0)
                end_time = insight.get("values", [{}])[0].get("end_time", "")
                date_recorded = end_time[:10] if end_time else post.get("created_time", "")[:10]
                # ถ้า value เป็น dict หรือ list ให้เก็บใน value_json
                if isinstance(value_obj, (dict, list)):
                    print(f"    Inserting insight metric: {metric_name}, value_json: {value_obj}")
                    cur.execute(
                        """
                        INSERT INTO facebook_post_insights (
                            post_id, metric_name, value_numeric, value_json, date_recorded, created_at
                        ) VALUES (%s, %s, NULL, %s, %s, now())
                        ON CONFLICT (post_id, metric_name, date_recorded) DO UPDATE SET
                            value_json=EXCLUDED.value_json,
                            created_at=now()
                        """,
                        (
                            post.get("id"),
                            metric_name,
                            json.dumps(value_obj),
                            date_recorded
                        )
                    )
                else:
                    print(f"    Inserting insight metric: {metric_name}, value_numeric: {value_obj}")
                    cur.execute(
                        """
                        INSERT INTO facebook_post_insights (
                            post_id, metric_name, value_numeric, value_json, date_recorded, created_at
                        ) VALUES (%s, %s, %s, NULL, %s, now())
                        ON CONFLICT (post_id, metric_name, date_recorded) DO UPDATE SET
                            value_numeric=EXCLUDED.value_numeric,
                            created_at=now()
                        """,
                        (
                            post.get("id"),
                            metric_name,
                            value_obj,
                            date_recorded
                        )
                    )

        # ดึง share_count และ comment_count
        post_fields_url = f"https://graph.facebook.com/v23.0/{post.get('id')}?fields=shares,comments.summary(true)&access_token={token}"
        post_fields_resp = requests.get(post_fields_url)
        post_fields_json = post_fields_resp.json()
        # share_count
        share_count = post_fields_json.get('shares', {}).get('count', 0)
        print(f"    Inserting insight metric: share_count, value_numeric: {share_count}")
        cur.execute(
            """
            INSERT INTO facebook_post_insights (
                post_id, metric_name, value_numeric, value_json, date_recorded, created_at
            ) VALUES (%s, %s, %s, NULL, %s, now())
            ON CONFLICT (post_id, metric_name, date_recorded) DO UPDATE SET
                value_numeric=EXCLUDED.value_numeric,
                created_at=now()
            """,
            (
                post.get("id"),
                "share_count",
                share_count,
                post.get("created_time", "")[:10]
            )
        )
        # comment_count
        comment_count = post_fields_json.get('comments', {}).get('summary', {}).get('total_count', 0)
        print(f"    Inserting insight metric: comment_count, value_numeric: {comment_count}")
        cur.execute(
            """
            INSERT INTO facebook_post_insights (
                post_id, metric_name, value_numeric, value_json, date_recorded, created_at
            ) VALUES (%s, %s, %s, NULL, %s, now())
            ON CONFLICT (post_id, metric_name, date_recorded) DO UPDATE SET
                value_numeric=EXCLUDED.value_numeric,
                created_at=now()
            """,
            (
                post.get("id"),
                "comment_count",
                comment_count,
                post.get("created_time", "")[:10]
            )
        )
    conn.commit()

cur.close()
conn.close()
print("Sync facebook_posts, facebook_post_attachments, facebook_post_insights success!")