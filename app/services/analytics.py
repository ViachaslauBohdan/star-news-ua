from __future__ import annotations

from app.db import Database


class AnalyticsService:
    def __init__(self, db: Database):
        self.db = db

    def summary(self) -> dict:
        with self.db.connect() as conn:
            totals = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM discovered_items) AS discovered,
                    (SELECT COUNT(*) FROM discovered_items WHERE status != 'irrelevant') AS relevant,
                    (SELECT COUNT(*) FROM published_posts) AS published
                """
            ).fetchone()
            top_artists = conn.execute(
                """
                SELECT artist_main AS name, COUNT(*) AS count
                FROM published_posts
                WHERE artist_main IS NOT NULL
                GROUP BY artist_main
                ORDER BY count DESC
                LIMIT 10
                """
            ).fetchall()
            top_categories = conn.execute(
                """
                SELECT category, COUNT(*) AS count
                FROM published_posts
                GROUP BY category
                ORDER BY count DESC
                """
            ).fetchall()
            top_sources = conn.execute(
                """
                SELECT source_name, COUNT(*) AS count
                FROM published_posts
                WHERE post_type = 'organic'
                GROUP BY source_name
                ORDER BY count DESC
                """
            ).fetchall()
            posts_per_day = conn.execute(
                """
                SELECT substr(published_at, 1, 10) AS day, COUNT(*) AS count
                FROM published_posts
                GROUP BY day
                ORDER BY day DESC
                LIMIT 14
                """
            ).fetchall()
            posting_hours = conn.execute(
                """
                SELECT substr(published_at, 12, 2) AS hour, COUNT(*) AS count
                FROM published_posts
                GROUP BY hour
                ORDER BY count DESC
                """
            ).fetchall()
        return {
            "total_discovered": totals["discovered"],
            "total_relevant": totals["relevant"],
            "total_published": totals["published"],
            "top_artists": [dict(row) for row in top_artists],
            "top_categories": [dict(row) for row in top_categories],
            "top_sources": [dict(row) for row in top_sources],
            "posts_per_day": [dict(row) for row in posts_per_day],
            "posting_hours": [dict(row) for row in posting_hours],
        }
