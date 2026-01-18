"""Vision Extractor - Uses Claude Vision API to extract BOM items from PDF images."""

import base64
import json
import re
from dataclasses import dataclass
from typing import List, Optional
import anthropic
from pdf2image import convert_from_path, convert_from_bytes


@dataclass
class ExtractedItem:
    """An item extracted from a BOM by Claude Vision."""
    description: str
    nsn: str = ""
    qty: int = 1
    confidence: str = "high"  # high, medium, low
    notes: str = ""


def pdf_to_images(pdf_path: str = None, pdf_bytes: bytes = None, dpi: int = 150) -> List[bytes]:
    """
    Convert a PDF to a list of PNG images (as bytes).
    
    Args:
        pdf_path: Path to PDF file (use this OR pdf_bytes)
        pdf_bytes: PDF file content as bytes
        dpi: Resolution for conversion (150 is good balance of quality/size)
        
    Returns:
        List of PNG image bytes, one per page
    """
    if pdf_path:
        images = convert_from_path(pdf_path, dpi=dpi)
    elif pdf_bytes:
        images = convert_from_bytes(pdf_bytes, dpi=dpi)
    else:
        raise ValueError("Must provide either pdf_path or pdf_bytes")
    
    image_bytes_list = []
    for img in images:
        import io
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        image_bytes_list.append(buffer.getvalue())
    
    return image_bytes_list


def extract_items_from_image(
    image_bytes: bytes,
    api_key: str,
    page_num: int = 1
) -> List[ExtractedItem]:
    """
    Use Claude Vision to extract BOM items from a single page image.
    
    Args:
        image_bytes: PNG image bytes
        api_key: Anthropic API key
        page_num: Page number (for context in the prompt)
        
    Returns:
        List of ExtractedItem objects
    """
    client = anthropic.Anthropic(api_key=api_key)
    
    # Encode image to base64
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    
    # Craft the extraction prompt
    prompt = """Analyze this Bill of Materials (BOM) / Component Listing / Hand Receipt page and extract all items.

For each item, extract:
1. **Description**: The item name/nomenclature (e.g., "WRENCH, ADJUSTABLE: 12 IN.")
2. **NSN/NIIN**: The National Stock Number if present (9-digit number, sometimes shown as 13-digit with dashes like 5120-00-123-4567)
3. **Quantity**: The authorized quantity (look for "Auth Qty", "OH Qty", or similar column)

IMPORTANT:
- Focus on items with Level "B" or items that are actual components (not headers like "COEI" or "BII")
- If handwritten annotations show different quantities, note them
- Include ALL items you can read, even if some fields are unclear
- For NSN, extract just the 9-digit NIIN if the full 13-digit NSN is shown

Return your response as a JSON array with this exact format:
```json
[
  {
    "description": "ITEM DESCRIPTION HERE",
    "nsn": "123456789",
    "qty": 2,
    "confidence": "high",
    "notes": "any relevant notes about this item"
  }
]
```

Confidence levels:
- "high": Clearly readable
- "medium": Partially readable or some uncertainty  
- "low": Difficult to read, guessing based on context

If there are no extractable items on this page, return an empty array: []"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"Page {page_num}: {prompt}"
                        }
                    ],
                }
            ],
        )
        
        # Parse the response
        response_text = response.content[0].text
        
        # Extract JSON from the response
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            items_data = json.loads(json_match.group())
            
            items = []
            for item in items_data:
                items.append(ExtractedItem(
                    description=item.get('description', '').strip(),
                    nsn=str(item.get('nsn', '')).strip(),
                    qty=int(item.get('qty', 1)),
                    confidence=item.get('confidence', 'medium'),
                    notes=item.get('notes', '')
                ))
            return items
        else:
            return []
            
    except Exception as e:
        print(f"Error extracting from page {page_num}: {e}")
        return []


def extract_items_from_pdf(
    api_key: str,
    pdf_path: str = None,
    pdf_bytes: bytes = None,
    start_page: int = 0,
    end_page: int = None,
    progress_callback=None
) -> List[ExtractedItem]:
    """
    Extract all BOM items from a PDF using Claude Vision.
    
    Args:
        api_key: Anthropic API key
        pdf_path: Path to PDF file (use this OR pdf_bytes)
        pdf_bytes: PDF file content as bytes
        start_page: First page to process (0-indexed)
        end_page: Last page to process (None = all pages)
        progress_callback: Optional function(page_num, total_pages, items_so_far) for progress updates
        
    Returns:
        List of all ExtractedItem objects from the PDF
    """
    # Convert PDF to images
    images = pdf_to_images(pdf_path=pdf_path, pdf_bytes=pdf_bytes)
    
    # Apply page range
    if end_page is None:
        end_page = len(images)
    images_to_process = images[start_page:end_page]
    
    all_items = []
    
    for i, img_bytes in enumerate(images_to_process):
        page_num = start_page + i + 1  # 1-indexed for display
        
        if progress_callback:
            progress_callback(page_num, len(images), len(all_items))
        
        page_items = extract_items_from_image(img_bytes, api_key, page_num)
        all_items.extend(page_items)
    
    # Deduplicate items by description (keep highest qty)
    seen = {}
    for item in all_items:
        key = item.description.upper()
        if key not in seen or item.qty > seen[key].qty:
            seen[key] = item
    
    return list(seen.values())



