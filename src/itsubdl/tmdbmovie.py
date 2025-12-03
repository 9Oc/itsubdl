import re

class TMDBMovie:
    def __init__(self, id, imdb_id, title, original_title, alternative_titles, year, duration, regions, watch_links):
        self.id = id
        self.imdb_id = imdb_id
        self.title = title
        self.original_title = original_title
        self.alternative_titles = alternative_titles
        self.year = year
        self.duration = duration
        self.regions = regions
        self.watch_links = watch_links
    
    def __repr__(self):
        return f"TMDBMovie(id={self.id}, title='{self.title}', original_title='{self.original_title}', year={self.year}, alternative_titles={self.alternative_titles}), duration={self.duration}"
        
    @staticmethod
    def sanitize(text):
        """Return a filesystem-safe version of a string."""
        if not text:
            return ""
        text = re.sub(r'[\/\\:\*\?"<>\|\-—·.,^]+', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
        
    @staticmethod
    def make_windows_safe(text: str) -> str:
        """
        Make a sanitized movie name safe for Windows filenames.
        Appends '_' to any reserved Windows device names (CON, PRN, AUX, NUL, COM1–COM9, LPT1–LPT9)
        while keeping the rest of the name intact.
        """
        reserved_names = {
            "CON","PRN","AUX","NUL",
            "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
            "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"
        }
    
        # split by dot to check each component
        parts = text.split(".")
        if parts and parts[0].upper() in reserved_names:
            parts[0] += "_"
        return ".".join(parts)
        
    @staticmethod
    def make_windows_safe_folder(text: str) -> str:
        #Make a movie title safe for Windows folder names.
        #- Replaces reserved words (CON, PRN, etc.) by appending '_'
        #- Keeps spaces instead of dots
        reserved_names = {
            "CON","PRN","AUX","NUL",
            "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
            "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"
        }

        # Split into words and fix reserved words
        parts = text.split()
        if parts and parts[0].upper() in reserved_names:
            parts[0] += "_"
        return " ".join(parts)