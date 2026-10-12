"""Video downloader for transdub.

Wraps the yt-dlp CLI to fetch a video and its subtitles, saving them under
`downloads/<YYYY-MM-DD>/<channel>/`, with parallel downloads and structured
results that the translation stage can consume.
"""
