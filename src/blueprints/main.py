from flask import Blueprint, request, jsonify, current_app, render_template, send_file, Response
import os
from datetime import datetime

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())

@main_bp.route('/api/current_image')
def get_current_image():
    """Serve current_image.png with conditional request support (If-Modified-Since)."""
    image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'current_image.png')
    
    if not os.path.exists(image_path):
        return jsonify({"error": "Image not found"}), 404
    
    # Get the file's last modified time (truncate to seconds to match HTTP header precision)
    file_mtime = int(os.path.getmtime(image_path))
    last_modified = datetime.fromtimestamp(file_mtime)
    
    # Check If-Modified-Since header
    if_modified_since = request.headers.get('If-Modified-Since')
    if if_modified_since:
        try:
            # Parse the If-Modified-Since header
            client_mtime = datetime.strptime(if_modified_since, '%a, %d %b %Y %H:%M:%S %Z')
            client_mtime_seconds = int(client_mtime.timestamp())
            
            # Compare (both now in seconds, no sub-second precision)
            if file_mtime <= client_mtime_seconds:
                return '', 304
        except (ValueError, AttributeError):
            pass
    
    # Send the file with Last-Modified header
    response = send_file(image_path, mimetype='image/png')
    response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
    response.headers['Cache-Control'] = 'no-cache'
    return response


@main_bp.route('/api/plugin_order', methods=['POST'])
def save_plugin_order():
    """Save the custom plugin order."""
    device_config = current_app.config['DEVICE_CONFIG']

    data = request.get_json() or {}
    order = data.get('order', [])

    if not isinstance(order, list):
        return jsonify({"error": "Order must be a list"}), 400

    device_config.set_plugin_order(order)

    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# ESP32 / thin-client endpoints
# ---------------------------------------------------------------------------

# Map of well-known display type names to their pixel dimensions.
_ESP32_DISPLAY_SIZES = {
    "epd2in13v2": (250, 122),
    "epd2in9v2":  (296, 128),
    "epd4in2":    (400, 300),
}


@main_bp.route('/api/esp32/image_data')
def esp32_image_data():
    """
    Return the current display image pre-processed for an ESP32 e-paper display.

    The response body is a raw 1-bit-per-pixel, row-major monochrome bitmap
    suitable for direct transfer to common Waveshare e-paper controllers.
    A set bit (1) represents WHITE; a cleared bit (0) represents BLACK.

    Query parameters
    ----------------
    display_type : str, optional
        One of: epd2in13v2, epd2in9v2, epd4in2.
        When provided, width/height are derived automatically.
    width : int, optional
        Target pixel width (used when display_type is not given).
    height : int, optional
        Target pixel height (used when display_type is not given).

    Response headers
    ----------------
    X-Width  : int  – pixel width of the returned bitmap
    X-Height : int  – pixel height of the returned bitmap
    Content-Type : application/octet-stream
    """
    from PIL import Image

    image_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'static', 'images', 'current_image.png',
    )

    if not os.path.exists(image_path):
        return jsonify({"error": "No current image available"}), 404

    # Resolve target dimensions
    display_type = request.args.get('display_type', '')
    if display_type in _ESP32_DISPLAY_SIZES:
        width, height = _ESP32_DISPLAY_SIZES[display_type]
    else:
        try:
            width  = int(request.args['width'])
            height = int(request.args['height'])
        except (KeyError, ValueError):
            return jsonify({
                "error": (
                    "Provide display_type or both width and height. "
                    f"Known display types: {list(_ESP32_DISPLAY_SIZES)}"
                )
            }), 400

    # Load, resize, and convert to 1-bit monochrome
    img = Image.open(image_path).convert('RGB')
    img = img.resize((width, height), Image.LANCZOS)
    img = img.convert('1')  # dither to 1-bit

    # Pack pixels into bytes (MSB first, 1 = white)
    row_bytes = (width + 7) // 8
    buf = bytearray(row_bytes * height)
    for y in range(height):
        for x in range(width):
            pixel = img.getpixel((x, y))
            # PIL '1' mode: 255 = white, 0 = black
            if pixel:
                buf[y * row_bytes + x // 8] |= (0x80 >> (x % 8))

    response = Response(bytes(buf), mimetype='application/octet-stream')
    response.headers['X-Width']  = str(width)
    response.headers['X-Height'] = str(height)
    response.headers['Cache-Control'] = 'no-cache'
    return response