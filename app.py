"""DD1750 Vision Assistant - Flask Application with access code system."""

import os
import tempfile
import json
import uuid
import hashlib
import secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for

from vision_extractor import (
    extract_items_from_pdf,
    pdf_to_images
)
from dd1750_generator import (
    generate_dd1750,
    DD1750Item,
    DD1750Header
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Get API key from environment (set this on Railway)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Admin password for generating access codes (set on Railway)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'change-this-password')

# Credit settings
FREE_EXTRACTIONS = int(os.environ.get('FREE_EXTRACTIONS', '3'))  # Free extractions per user

# Access codes storage
# Format: {code: {'credits': int, 'used': bool, 'used_by': user_id, 'created': timestamp}}
# In production, use Redis or database
ACCESS_CODES = {}

# User data storage
# Format: {user_id: {'extractions_used': int, 'credits': int}}
USER_DATA = {}
TEMP_STORAGE = {}


def get_user_id():
    """Get or create a persistent user ID from session."""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        session.permanent = True
    return session['user_id']


def get_user_data(user_id):
    """Get user data, creating default if needed."""
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {
            'extractions_used': 0,
            'credits': 0,
            'total_paid': 0
        }
    return USER_DATA[user_id]


def get_remaining_extractions(user_id):
    """Calculate remaining extractions for a user."""
    data = get_user_data(user_id)
    free_remaining = max(0, FREE_EXTRACTIONS - data['extractions_used'])
    return free_remaining + data['credits']


def use_extraction(user_id):
    """Use one extraction credit. Returns True if successful."""
    data = get_user_data(user_id)
    
    # First use free extractions
    if data['extractions_used'] < FREE_EXTRACTIONS:
        data['extractions_used'] += 1
        return True
    
    # Then use paid credits
    if data['credits'] > 0:
        data['credits'] -= 1
        return True
    
    return False


def check_api_configured():
    """Check if the API key is configured."""
    return bool(ANTHROPIC_API_KEY)


@app.route('/')
def index():
    """Render the main application page."""
    user_id = get_user_id()
    remaining = get_remaining_extractions(user_id)
    
    return render_template('index.html',
        remaining_extractions=remaining,
        free_extractions=FREE_EXTRACTIONS,
        api_configured=check_api_configured()
    )


@app.route('/status')
def get_status():
    """Get current user status."""
    user_id = get_user_id()
    remaining = get_remaining_extractions(user_id)
    data = get_user_data(user_id)
    
    return jsonify({
        'remaining_extractions': remaining,
        'free_used': data['extractions_used'],
        'free_total': FREE_EXTRACTIONS,
        'credits': data['credits'],
        'api_configured': check_api_configured()
    })


@app.route('/upload', methods=['POST'])
def upload_pdf():
    """Handle PDF upload and convert to images for preview."""
    if 'bom_file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['bom_file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400
    
    try:
        user_id = get_user_id()
        pdf_bytes = file.read()
        
        # Store the PDF temporarily
        TEMP_STORAGE[f"{user_id}_pdf"] = pdf_bytes
        TEMP_STORAGE[f"{user_id}_filename"] = file.filename
        
        # Convert to images for preview
        images = pdf_to_images(pdf_bytes=pdf_bytes, dpi=100)
        
        # Store image count
        TEMP_STORAGE[f"{user_id}_pages"] = len(images)
        
        # Create base64 thumbnails for preview
        import base64
        thumbnails = []
        for i, img_bytes in enumerate(images):
            b64 = base64.b64encode(img_bytes).decode('utf-8')
            thumbnails.append({
                'page': i + 1,
                'data': f'data:image/png;base64,{b64}'
            })
        
        return jsonify({
            'success': True,
            'filename': file.filename,
            'pages': len(images),
            'thumbnails': thumbnails
        })
        
    except Exception as e:
        return jsonify({'error': f'Error processing PDF: {str(e)}'}), 500


@app.route('/extract', methods=['POST'])
def extract_items():
    """Extract items from the uploaded PDF using Claude Vision."""
    if not check_api_configured():
        return jsonify({'error': 'Service not configured. Please contact administrator.'}), 503
    
    user_id = get_user_id()
    remaining = get_remaining_extractions(user_id)
    
    if remaining <= 0:
        return jsonify({
            'error': 'No extractions remaining. Please purchase credits to continue.',
            'need_credits': True
        }), 402
    
    data = request.get_json()
    start_page = int(data.get('start_page', 0))
    end_page = data.get('end_page')
    if end_page:
        end_page = int(end_page)
    
    pdf_bytes = TEMP_STORAGE.get(f"{user_id}_pdf")
    
    if not pdf_bytes:
        return jsonify({'error': 'No PDF uploaded. Please upload a file first.'}), 400
    
    try:
        # Use one extraction credit
        if not use_extraction(user_id):
            return jsonify({
                'error': 'No extractions remaining.',
                'need_credits': True
            }), 402
        
        # Extract items using Claude Vision
        items = extract_items_from_pdf(
            api_key=ANTHROPIC_API_KEY,
            pdf_bytes=pdf_bytes,
            start_page=start_page,
            end_page=end_page
        )
        
        # Convert to serializable format
        items_data = []
        for i, item in enumerate(items):
            items_data.append({
                'id': i + 1,
                'description': item.description,
                'nsn': item.nsn,
                'qty': item.qty,
                'confidence': item.confidence,
                'notes': item.notes,
                'unit_of_issue': 'EA'
            })
        
        # Store extracted items
        TEMP_STORAGE[f"{user_id}_items"] = items_data
        
        # Get updated remaining count
        new_remaining = get_remaining_extractions(user_id)
        
        return jsonify({
            'success': True,
            'items': items_data,
            'count': len(items_data),
            'remaining_extractions': new_remaining
        })
        
    except Exception as e:
        # Refund the credit on error
        get_user_data(user_id)['credits'] += 1
        return jsonify({'error': f'Extraction failed: {str(e)}'}), 500


@app.route('/generate', methods=['POST'])
def generate_form():
    """Generate the DD1750 PDF from the extracted/edited items."""
    user_id = get_user_id()
    data = request.get_json()
    items_data = data.get('items', [])
    header_data = data.get('header', {})
    
    if not items_data:
        items_data = TEMP_STORAGE.get(f"{user_id}_items", [])
    
    if not items_data:
        return jsonify({'error': 'No items to generate. Please extract or add items first.'}), 400
    
    try:
        # Convert to DD1750Item objects
        dd1750_items = []
        for i, item in enumerate(items_data):
            qty = int(item.get('qty', 1))
            dd1750_items.append(DD1750Item(
                line_no=i + 1,
                description=item.get('description', ''),
                nsn=item.get('nsn', ''),
                unit_of_issue=item.get('unit_of_issue', 'EA'),
                initial_qty=qty,
                spares_qty=0,
                total_qty=qty
            ))
        
        # Create header
        header = DD1750Header(
            packed_by=header_data.get('packed_by', ''),
            no_boxes=header_data.get('no_boxes', ''),
            requisition_no=header_data.get('requisition_no', ''),
            order_no=header_data.get('order_no', ''),
            end_item=header_data.get('end_item', ''),
            date=header_data.get('date', datetime.now().strftime('%Y-%m-%d')),
            certifier_name=header_data.get('certifier_name', ''),
            certifier_title=header_data.get('certifier_title', '')
        )
        
        # Generate the PDF
        template_path = os.path.join(os.path.dirname(__file__), 'blank_1750.pdf')
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            output_path = tmp.name
        
        generate_dd1750(dd1750_items, template_path, output_path, header)
        
        # Store the output path for download
        TEMP_STORAGE[f"{user_id}_output"] = output_path
        
        return jsonify({
            'success': True,
            'message': f'Generated DD1750 with {len(dd1750_items)} items'
        })
        
    except Exception as e:
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500


@app.route('/download')
def download_pdf():
    """Download the generated DD1750 PDF."""
    user_id = get_user_id()
    output_path = TEMP_STORAGE.get(f"{user_id}_output")
    
    if not output_path or not os.path.exists(output_path):
        return "No generated PDF found. Please generate first.", 404
    
    filename = f"DD1750_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return send_file(
        output_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


@app.route('/clear')
def clear_session():
    """Clear the current session data (but keep credits)."""
    user_id = get_user_id()
    
    # Clean up temp files
    output_path = TEMP_STORAGE.get(f"{user_id}_output")
    if output_path and os.path.exists(output_path):
        try:
            os.remove(output_path)
        except:
            pass
    
    # Clear temp storage but NOT user credits
    keys_to_remove = [k for k in TEMP_STORAGE if k.startswith(user_id)]
    for key in keys_to_remove:
        del TEMP_STORAGE[key]
    
    return jsonify({'success': True})


# ============ ACCESS CODE ROUTES ============

@app.route('/redeem-code', methods=['POST'])
def redeem_code():
    """Redeem an access code for extraction credits."""
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    
    if not code:
        return jsonify({'error': 'Please enter an access code'}), 400
    
    if code not in ACCESS_CODES:
        return jsonify({'error': 'Invalid access code'}), 400
    
    code_data = ACCESS_CODES[code]
    
    if code_data['used']:
        return jsonify({'error': 'This code has already been used'}), 400
    
    # Mark code as used and add credits to user
    user_id = get_user_id()
    code_data['used'] = True
    code_data['used_by'] = user_id
    code_data['used_at'] = datetime.now().isoformat()
    
    user_data = get_user_data(user_id)
    user_data['credits'] += code_data['credits']
    
    new_remaining = get_remaining_extractions(user_id)
    
    return jsonify({
        'success': True,
        'credits_added': code_data['credits'],
        'remaining_extractions': new_remaining,
        'message': f'Added {code_data["credits"]} extractions to your account!'
    })


# ============ ADMIN ROUTES ============

@app.route('/admin')
def admin_page():
    """Render admin page for generating access codes."""
    return render_template('admin.html')


@app.route('/admin/generate-codes', methods=['POST'])
def generate_codes():
    """Generate new access codes (admin only)."""
    data = request.get_json()
    password = data.get('password', '')
    
    if password != ADMIN_PASSWORD:
        return jsonify({'error': 'Invalid admin password'}), 401
    
    num_codes = int(data.get('num_codes', 1))
    credits_per_code = int(data.get('credits', 25))
    
    if num_codes < 1 or num_codes > 100:
        return jsonify({'error': 'Number of codes must be between 1 and 100'}), 400
    
    if credits_per_code < 1 or credits_per_code > 1000:
        return jsonify({'error': 'Credits per code must be between 1 and 1000'}), 400
    
    # Generate codes
    new_codes = []
    for _ in range(num_codes):
        # Generate a readable code like "DD17-ABCD-1234"
        code = f"DD17-{secrets.token_hex(2).upper()}-{secrets.randbelow(9000) + 1000}"
        
        ACCESS_CODES[code] = {
            'credits': credits_per_code,
            'used': False,
            'used_by': None,
            'created': datetime.now().isoformat()
        }
        new_codes.append(code)
    
    return jsonify({
        'success': True,
        'codes': new_codes,
        'credits_per_code': credits_per_code
    })


@app.route('/admin/list-codes', methods=['POST'])
def list_codes():
    """List all access codes (admin only)."""
    data = request.get_json()
    password = data.get('password', '')
    
    if password != ADMIN_PASSWORD:
        return jsonify({'error': 'Invalid admin password'}), 401
    
    codes_list = []
    for code, data in ACCESS_CODES.items():
        codes_list.append({
            'code': code,
            'credits': data['credits'],
            'used': data['used'],
            'used_by': data.get('used_by'),
            'created': data['created'],
            'used_at': data.get('used_at')
        })
    
    # Sort by created date, newest first
    codes_list.sort(key=lambda x: x['created'], reverse=True)
    
    return jsonify({
        'success': True,
        'codes': codes_list,
        'total': len(codes_list),
        'unused': sum(1 for c in codes_list if not c['used'])
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
