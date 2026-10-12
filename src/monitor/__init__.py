"""Channel monitoring and notification for transdub.

Watches a category-grouped channel list via the YouTube Data API, detects new
uploads and same-category "trending" videos (filtering out ones without
captions), and emails a digest of candidates to review.
"""
