"""Bounded render windows; OCR can run concurrently without sharing PDF handles."""
def page_ocr_batches(document, render, recognize, *, always_ocr=False):
    for start in range(0, len(document), 2):
        rows=[]
        for index in range(start,min(start+2,len(document))):
            page=None; text=''; png=None; error=None
            try:
                page=document.load_page(index)
                text=page.get_text('text')
                if not isinstance(text,str):raise ValueError('Invalid extracted text')
                text=text.strip()
                if always_ocr or not text or page.get_images() or page.get_drawings():
                    png=render(page)
            except Exception as caught:error=caught
            rows.append([index,page,text,png,None,error])
        pending=[row for row in rows if row[3] is not None and row[5] is None]
        if pending:
            try:
                results=recognize([row[3] for row in pending])
                if len(results)!=len(pending):raise ValueError('OCR result count mismatch')
                for row,result in zip(pending,results):row[4]=result
            except Exception as caught:
                for row in pending:row[5]=caught
        yield from rows
