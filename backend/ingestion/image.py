"""Image material ingestion with original location, OCR and optional vision."""
import os
from backend.image_processing import image_png
from backend.preparation_progress import report
from .ocr import extract_image_text
from .utils import generate_unit_id


def ingest_image(data: bytes,filename: str) -> tuple[list[dict],list[str]]:
    png=image_png(data)
    report('reading_image',0,1)
    text,metadata,warnings=extract_image_text(png)
    source={'filename':filename,'file_type':'image'}
    location={'kind':'page','page_number':1,'original_image':True,**metadata}
    units=[]
    if text.strip():
        units.append({'unit_id':generate_unit_id(filename,'image_ocr','1'),'source':source,
            'text':'Recognized text from uploaded image (OCR; check small labels against the original):\n'+text,
            'source_location':location,'extraction_status':'ocr','warnings':warnings})
    if os.getenv('OLLAMA_VISION_MODEL','').strip():
        from backend.figure_tools import interpret_image
        try:
            result=interpret_image(png,'Describe the actual visible subject in English, including text, diagrams, photos or scenes. Explain educational concepts when present, clearly visible labels and relationships; state uncertainty. Do not require the image to be a diagram.')
            if result['answerable']:
                visual='\n'.join(result['observations'])+'\n'+result['explanation']
                if result.get('limitations'):visual+='\nLimitations: '+'; '.join(result['limitations'])
                units.append({'unit_id':generate_unit_id(filename,'image_vision','1'),'source':source,
                    'text':'Visual interpretation of uploaded image (model checked; not independently fact verified):\n'+visual,
                    'source_location':{**location,'visual_interpretation':True},
                    'extraction_status':'vision_model_checked','warnings':[]})
            else:warnings.append('The vision model could not interpret this image reliably.')
        except Exception:
            warnings.append('Vision interpretation was unavailable. Readable OCR text is preserved; check your configured vision model.')
    elif not text.strip():
        warnings.append('No readable text was found. Configure OLLAMA_VISION_MODEL for diagrams/photos without text, then retry preparation.')
    report('reading_image',1,1)
    return units,warnings
