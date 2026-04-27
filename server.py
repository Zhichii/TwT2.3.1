import json
from flask import Flask, Response, request, jsonify, render_template, stream_with_context

import log
from app import App

app = Flask(__name__)
chat_app = App()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat/<chat_uuid>')
def chat_by_uuid(chat_uuid):
    return render_template('index.html')

@app.route('/settings')
def settings_page():
    return render_template('index.html')


@app.route('/api/state')
def get_state():
    chat_uuid = request.args.get('uuid')
    providers = chat_app.get_providers_json()
    chats = chat_app.get_chats_list()
    state = chat_app.get_current_state(chat_uuid)
    messages = chat_app.get_chat_messages(chat_uuid) if chat_uuid else []
    response = jsonify({
        "providers": providers,
        "chats": chats,
        "state": state,
        "messages": messages,
    })
    response.headers["Cache-Control"] = "0"
    print(response)
    return response


@app.route('/api/chat/send', methods=['POST'])
def send_message():
    data = request.get_json()
    msg = data.get('message', '')
    files = data.get('files', [])
    chat_uuid = data.get('uuid')
    language = data.get('language', 'en')

    def generate():
        for event in chat_app.chats.stream_message(msg, chat_uuid, files=files, language=language):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'close',
            'X-Accel-Buffering': 'no',
        },
    )


@app.route('/api/chat/new', methods=['POST'])
def new_chat():
    chat_app.new_chat()
    return jsonify({"success": True})


@app.route('/api/chat/switch', methods=['POST'])
def switch_chat():
    data = request.get_json()
    uuid = data.get('uuid')
    if uuid and chat_app.switch_chat_by_uuid(uuid):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid uuid"}), 400


@app.route('/api/chat/delete', methods=['POST'])
def delete_chat():
    data = request.get_json()
    uuid = data.get('uuid')
    if uuid and chat_app.delete_chat_by_uuid(uuid):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid uuid"}), 400


@app.route('/api/model/select', methods=['POST'])
def select_model():
    data = request.get_json()
    provider_index = data.get('provider_index')
    model_index = data.get('model_index')
    chat_uuid = data.get('uuid')
    if provider_index is not None and model_index is not None:
        chat_app.select_provider(provider_index, model_index, chat_uuid)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid indices"}), 400


@app.route('/api/thinking/stage', methods=['PATCH'])
def set_thinking_stage():
    data = request.get_json()
    stage = data.get('stage')
    chat_uuid = data.get('uuid')
    if stage is not None and not isinstance(stage, int):
        return jsonify({"success": False, "error": "Stage must be an integer or null"}), 400
    chat_app.set_thinking_stage(stage, chat_uuid)
    return jsonify({"success": True})


@app.route('/api/provider/add', methods=['POST'])
def add_provider():
    data = request.get_json()
    name = data.get('name', '').strip()
    base_url = data.get('base_url', '').strip()
    api_key = data.get('api_key', '').strip()
    ptype = data.get('type', 'openai')
    if not name or not base_url or not api_key:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    chat_app.add_provider(name, base_url, api_key, ptype)
    return jsonify({"success": True})


@app.route('/api/provider/<int:index>', methods=['DELETE'])
def delete_provider(index):
    providers = chat_app.providers.providers
    if 0 <= index < len(providers):
        del providers[index]
        del chat_app.cfg["providers"][index]
        chat_app.cfg.save()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid index"}), 400


@app.route('/api/provider/templates', methods=['GET'])
def get_model_templates():
    return jsonify({"templates": chat_app.get_model_templates()})


@app.route('/api/provider/<int:index>/models/recognize', methods=['GET'])
def recognize_models(index):
    models = chat_app.get_recognized_models(index)
    return jsonify({"models": models})


@app.route('/api/provider/<int:index>/models/add', methods=['POST'])
def add_model_to_provider(index):
    data = request.get_json()
    if not data or not data.get('id'):
        return jsonify({"success": False, "error": "Missing model id"}), 400
    success = chat_app.add_model_to_provider(index, {
        "id": data.get('id', '').strip(),
        "name": data.get('name', '').strip(),
        "template": data.get('template')
    })
    if success:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Failed to add model (duplicate or invalid provider)"}), 400


@app.route('/api/provider/<int:pindex>/models/<int:midx>', methods=['DELETE'])
def delete_model_from_provider(pindex, midx):
    success = chat_app.delete_model_from_provider(pindex, midx)
    if success:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid provider or model index"}), 400


@app.route('/api/chat/<uuid:chat_uuid>/rename', methods=['PATCH'])
def rename_chat(chat_uuid):
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400
    if chat_app.rename_chat(str(chat_uuid), title):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid chat"}), 400


@app.route('/api/chat/<uuid:chat_uuid>/rename-ai', methods=['POST'])
def rename_chat_ai(chat_uuid):
    if chat_app.rename_chat_ai(str(chat_uuid)):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid chat or no messages"}), 400


@app.route('/api/chat/message/edit', methods=['POST'])
def edit_message():
    data = request.get_json()
    msg_id = data.get('msg_id')
    content = data.get('content', '').strip()
    chat_uuid = data.get('uuid')
    if msg_id is None or not content or not chat_uuid:
        return jsonify({"success": False, "error": "msg_id, uuid and content required"}), 400
    if chat_app.edit_user_message(chat_uuid, msg_id, content):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Cannot edit message"}), 400


@app.route('/api/system-prompt', methods=['GET'])
def get_system_prompt():
    return jsonify({"system_prompt": chat_app.get_system_prompt()})


@app.route('/api/system-prompt', methods=['PATCH'])
def set_system_prompt():
    data = request.get_json()
    value = data.get('system_prompt', '')
    chat_app.set_system_prompt(value)
    return jsonify({"success": True})


if __name__ == '__main__':
    log.hint("Starting TwT2.3 Web UI on http://0.0.0.0:5004")
    app.run(host='0.0.0.0', port=5004, debug=False, threaded=True)
