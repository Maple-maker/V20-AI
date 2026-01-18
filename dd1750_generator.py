"""DD1750 PDF Generator - Creates filled DD1750 forms from extracted items."""

import io
import math
from dataclasses import dataclass
from typing import List, Optional

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


# DD1750 Form Layout Constants (from Project 1)
ROWS_PER_PAGE = 18
PAGE_W, PAGE_H = 612.0, 792.0

# Column X positions (left, right)
X_BOX_L, X_BOX_R = 44.0, 88.0
X_CONTENT_L, X_CONTENT_R = 88.0, 365.0
X_UOI_L, X_UOI_R = 365.0, 408.5
X_INIT_L, X_INIT_R = 408.5, 453.5
X_SPARES_L, X_SPARES_R = 453.5, 514.5
X_TOTAL_L, X_TOTAL_R = 514.5, 566.0

# Row Y positions
Y_TABLE_TOP_LINE = 616.0
Y_TABLE_BOTTOM_LINE = 89.5
ROW_H = (Y_TABLE_TOP_LINE - Y_TABLE_BOTTOM_LINE) / ROWS_PER_PAGE
PAD_X = 3.0

# Header field positions
HEADER_Y = {
    'packed_by': 735.0,
    'no_boxes': 735.0,
    'req_no': 735.0,
    'order_no': 710.0,
    'end_item': 685.0,
    'date': 685.0,
    'page': 660.0,
}

HEADER_X = {
    'packed_by': 95.0,
    'no_boxes': 240.0,
    'req_no': 370.0,
    'order_no': 370.0,
    'end_item': 95.0,
    'date': 500.0,
    'page_num': 500.0,
    'page_total': 545.0,
}


@dataclass
class DD1750Item:
    """Represents a single item for the DD1750 form."""
    line_no: int
    description: str
    nsn: str = ""
    unit_of_issue: str = "EA"
    initial_qty: int = 1
    spares_qty: int = 0
    total_qty: int = 1


@dataclass
class DD1750Header:
    """Header information for the DD1750 form."""
    packed_by: str = ""
    no_boxes: str = ""
    requisition_no: str = ""
    order_no: str = ""
    end_item: str = ""
    date: str = ""
    certifier_name: str = ""
    certifier_title: str = ""


def generate_dd1750(
    items: List[DD1750Item],
    template_path: str,
    output_path: str,
    header: Optional[DD1750Header] = None
) -> tuple[str, int]:
    """
    Generate a filled DD1750 PDF from a list of items.
    
    Args:
        items: List of DD1750Item objects to include
        template_path: Path to the blank DD1750 template PDF
        output_path: Path where the output PDF will be saved
        header: Optional DD1750Header with form header information
        
    Returns:
        Tuple of (output_path, item_count)
    """
    if not items:
        # Return blank template if no items
        reader = PdfReader(template_path)
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        with open(output_path, 'wb') as f:
            writer.write(f)
        return output_path, 0
    
    total_pages = math.ceil(len(items) / ROWS_PER_PAGE)
    writer = PdfWriter()
    
    for page_num in range(total_pages):
        start_idx = page_num * ROWS_PER_PAGE
        end_idx = min((page_num + 1) * ROWS_PER_PAGE, len(items))
        page_items = items[start_idx:end_idx]
        
        # Create overlay
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(PAGE_W, PAGE_H))
        
        # Add header info (on first page or all pages)
        if header:
            _draw_header(can, header, page_num + 1, total_pages)
        else:
            # Just draw page numbers
            can.setFont("Helvetica", 10)
            can.drawString(HEADER_X['page_num'], HEADER_Y['page'], str(page_num + 1))
            can.drawString(HEADER_X['page_total'], HEADER_Y['page'], str(total_pages))
        
        # Draw items
        first_row_top = Y_TABLE_TOP_LINE - 5.0
        
        for i, item in enumerate(page_items):
            y = first_row_top - (i * ROW_H)
            y_desc = y - 7.0
            y_nsn = y - 17.0
            
            # Box number (line number)
            can.setFont("Helvetica", 8)
            can.drawCentredString((X_BOX_L + X_BOX_R) / 2, y_desc, str(item.line_no))
            
            # Description (truncate if needed)
            can.setFont("Helvetica", 7)
            desc = item.description[:50] if len(item.description) > 50 else item.description
            can.drawString(X_CONTENT_L + PAD_X, y_desc, desc)
            
            # NSN (if present)
            if item.nsn:
                can.setFont("Helvetica", 6)
                can.drawString(X_CONTENT_L + PAD_X, y_nsn, f"NSN: {item.nsn}")
            
            # Unit of Issue
            can.setFont("Helvetica", 8)
            can.drawCentredString((X_UOI_L + X_UOI_R) / 2, y_desc, item.unit_of_issue)
            
            # Initial Operation Qty
            can.drawCentredString((X_INIT_L + X_INIT_R) / 2, y_desc, str(item.initial_qty))
            
            # Running Spares Qty
            can.drawCentredString((X_SPARES_L + X_SPARES_R) / 2, y_desc, str(item.spares_qty))
            
            # Total Qty
            can.drawCentredString((X_TOTAL_L + X_TOTAL_R) / 2, y_desc, str(item.total_qty))
        
        can.save()
        packet.seek(0)
        
        # Merge overlay with template
        overlay = PdfReader(packet)
        page = PdfReader(template_path).pages[0]
        page.merge_page(overlay.pages[0])
        writer.add_page(page)
    
    with open(output_path, 'wb') as f:
        writer.write(f)
    
    return output_path, len(items)


def _draw_header(can: canvas.Canvas, header: DD1750Header, page_num: int, total_pages: int):
    """Draw header information on the canvas."""
    can.setFont("Helvetica", 10)
    
    # Packed By
    if header.packed_by:
        can.drawString(HEADER_X['packed_by'], HEADER_Y['packed_by'], header.packed_by)
    
    # Number of Boxes
    if header.no_boxes:
        can.drawString(HEADER_X['no_boxes'], HEADER_Y['no_boxes'], header.no_boxes)
    
    # Requisition Number
    if header.requisition_no:
        can.drawString(HEADER_X['req_no'], HEADER_Y['req_no'], header.requisition_no)
    
    # Order Number
    if header.order_no:
        can.drawString(HEADER_X['order_no'], HEADER_Y['order_no'], header.order_no)
    
    # End Item
    if header.end_item:
        can.setFont("Helvetica", 8)
        can.drawString(HEADER_X['end_item'], HEADER_Y['end_item'], header.end_item[:60])
    
    # Date
    can.setFont("Helvetica", 10)
    if header.date:
        can.drawString(HEADER_X['date'], HEADER_Y['date'], header.date)
    
    # Page numbers
    can.drawString(HEADER_X['page_num'], HEADER_Y['page'], str(page_num))
    can.drawString(HEADER_X['page_total'], HEADER_Y['page'], str(total_pages))
    
    # Certifier info at bottom
    if header.certifier_name or header.certifier_title:
        can.setFont("Helvetica", 9)
        cert_y = 55.0
        if header.certifier_name:
            can.drawString(95.0, cert_y, header.certifier_name)
        if header.certifier_title:
            can.drawString(280.0, cert_y, header.certifier_title)
