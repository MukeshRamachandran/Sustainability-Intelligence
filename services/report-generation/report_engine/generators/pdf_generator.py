import os
import uuid
import logging
from jinja2 import Environment, FileSystemLoader
from .asset_manager import AssetManager

logger = logging.getLogger(__name__)

def generate_pdf_report(data: dict, config) -> str:
    """Renders HTML from Jinja2 and generates a PDF using WeasyPrint."""
    from weasyprint import HTML, CSS
    
    # Initialize asset manager
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    asset_mgr = AssetManager(project_root)
    
    # Pass the asset manager to the template data
    data['assets'] = asset_mgr
    
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Render the master report assembler template instead of static layout
    template = env.get_template("report_assembler.html")
    html_content = template.render(**data)
    
    export_dir = os.path.join(os.path.dirname(__file__), "..", "exports")
    os.makedirs(export_dir, exist_ok=True)
    
    with open(os.path.join(export_dir, "debug.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
        
    os.makedirs(export_dir, exist_ok=True)
    
    filename = f"Sustainability_Report_{data.get('month', 'all')}_{data['year']}_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = os.path.join(export_dir, filename)
    
    # Ensure relative links map back to the project root properly
    base_url = f"file:///{project_root.replace(os.sep, '/')}/"
    
    HTML(string=html_content, base_url=base_url).write_pdf(pdf_path)
    
    return pdf_path
