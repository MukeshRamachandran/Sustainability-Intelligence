import os
import base64
import logging

logger = logging.getLogger(__name__)

class AssetManager:
    def __init__(self, project_root: str = None):
        if project_root is None:
            # Standalone mode: root is two directories up (pdf_export_module)
            self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        else:
            self.project_root = project_root
            
        self.assets_dir = os.path.join(self.project_root, "assets", "report")
        self.fonts_dir = os.path.join(self.assets_dir, "fonts")
        
        if not os.path.exists(self.fonts_dir):
            os.makedirs(self.fonts_dir, exist_ok=True)

    def get_asset_uri(self, filename: str) -> str:
        """Returns the absolute file:/// URI for WeasyPrint to reliably load assets."""
        path = os.path.join(self.assets_dir, filename)
        if os.path.exists(path):
            # WeasyPrint prefers file:///C:/path/to/file format on Windows
            normalized_path = path.replace(os.sep, '/')
            if not normalized_path.startswith('/'):
                normalized_path = '/' + normalized_path
            return f"file://{normalized_path}"
        logger.warning(f"Asset not found: {path}")
        return ""

    def get_base64_image(self, filename: str) -> str:
        """Returns base64 string for an image, useful for embedding directly."""
        path = os.path.join(self.assets_dir, filename)
        if not os.path.exists(path):
            logger.warning(f"Base64 Asset not found: {path}")
            return ""
        
        ext = filename.split('.')[-1].lower()
        mime_type = "image/png"
        if ext in ['jpg', 'jpeg']:
            mime_type = "image/jpeg"
        elif ext == 'svg':
            mime_type = "image/svg+xml"
            
        try:
            with open(path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                return f"data:{mime_type};base64,{encoded_string}"
        except Exception as e:
            logger.error(f"Error encoding {path}: {e}")
            return ""

    def get_font_face_css(self) -> str:
        """Generates @font-face CSS rules for embedded fonts."""
        # We will embed Public Sans and Archivo
        fonts_css = ""
        font_configs = {
            "Archivo": ["Archivo-Regular.ttf", "Archivo-Medium.ttf", "Archivo-SemiBold.ttf", "Archivo-Bold.ttf"],
            "Public Sans": ["PublicSans-Regular.ttf", "PublicSans-Medium.ttf", "PublicSans-SemiBold.ttf", "PublicSans-Bold.ttf"]
        }
        
        weights = {
            "Regular": 400,
            "Medium": 500,
            "SemiBold": 600,
            "Bold": 700
        }
        
        for family, files in font_configs.items():
            for file in files:
                path = os.path.join(self.fonts_dir, file)
                if os.path.exists(path):
                    weight_str = file.split('-')[1].split('.')[0]
                    weight = weights.get(weight_str, 400)
                    
                    normalized_path = path.replace(os.sep, '/')
                    if not normalized_path.startswith('/'):
                        normalized_path = '/' + normalized_path
                    uri = f"file://{normalized_path}"
                    
                    fonts_css += f"""
                    @font-face {{
                        font-family: '{family}';
                        src: url('{uri}') format('truetype');
                        font-weight: {weight};
                        font-style: normal;
                    }}
                    """
        return fonts_css
