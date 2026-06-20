import os
import json
import pdfplumber
import anthropic
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MONDAY_API_KEY = os.environ.get("MONDAY_API_KEY")
MONDAY_BOARD_ID = os.environ.get("MONDAY_BOARD_ID", "18390622308")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

LOCAIS = ["Galpão Campeiro", "Moveis", "Padrão", "Secretaria"]
DEPARTAMENTOS = ["Cozinha", "Bolicho", "Secretaria", "Depto Artístico", "Tesouraria", "Capatazia", "Patronagem", "Depto Cultural"]
LOCAIS_ITEM = ["Salão da Igreja", "Galpão Campeiro", "Resid. do Responsável"]
CANAIS = ["Mercado Livre", "Shopee", "Magalu", "Outro"]

def extrair_texto_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() or ""
    return texto

def extrair_dados_nf(texto):
    prompt = (
        "Voce e um especialista em notas fiscais brasileiras.\n"
        "Analise o texto abaixo de uma NF-e e extraia as informacoes em JSON.\n\n"
        "Retorne APENAS um JSON valido, sem explicacoes, sem markdown, sem backticks.\n\n"
        "Formato esperado:\n"
        '{"numero_nf": "000.071.604", "data_emissao": "2026-06-03", "fornecedor": "Nome do fornecedor", '
        '"canal_compra": "Mercado Livre", "itens": [{"nome": "Nome do produto", "quantidade": 1, "valor_unitario": 346.64}]}\n\n'
        "Para canal_compra, tente identificar se e: Mercado Livre, Shopee, Magalu. Se nao identificar, coloque Outro.\n\n"
        "Texto da NF:\n" + texto
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(message.content[0].text.strip())

def criar_label_monday(column_id, label):
    url = "https://api.monday.com/v2"
    headers = {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}
    query = """mutation ($board: ID!, $column: String!, $label: String!) {
        create_label_for_column(board_id: $board, column_id: $column, label: $label) { id label }
    }"""
    variables = {"board": int(MONDAY_BOARD_ID), "column": column_id, "label": label}
    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    result = response.json()
    return result.get("data", {}).get("create_label_for_column", {}).get("id")

def criar_item_monday(item, numero_nf, data_emissao, local, canal_compra, departamento, local_item, obs_local):
    url = "https://api.monday.com/v2"
    headers = {"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"}

    col_values = {
        "data": {"date": data_emissao if data_emissao else ""},
        "text_mm4gqxsy": numero_nf,
        "numeric_mky8bk22": item["valor_unitario"],
        "numeric_mm2wge9s": item["quantidade"],
        "text_mm4f77m6": canal_compra,
        "dropdown_mm2s9w16": {"labels": [local]},
        "color_mm4g90ps": {"index": 0},
    }

    if departamento:
        col_values["color_mm4gtmap"] = {"label": departamento}
    if local_item:
        col_values["color_mm4gaz07"] = {"label": local_item}
    if obs_local:
        col_values["text_mm4gx1tb"] = obs_local

    query = "mutation ($board: ID!, $item_name: String!, $column_values: JSON!) { create_item(board_id: $board, item_name: $item_name, column_values: $column_values) { id } }"
    variables = {
        "board": int(MONDAY_BOARD_ID),
        "item_name": item["nome"],
        "column_values": json.dumps(col_values)
    }
    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    result = response.json()
    return result["data"]["create_item"]["id"]

def anexar_pdf_monday(item_id, pdf_bytes, filename):
    url = "https://api.monday.com/v2/file"
    headers = {"Authorization": MONDAY_API_KEY}
    query = 'mutation ($file: File!) { add_file_to_column(item_id: %s, column_id: "file_mky8cexx", file: $file) { id } }' % item_id
    files = {
        "query": (None, query),
        "variables[file]": (filename, pdf_bytes, "application/pdf")
    }
    requests.post(url, headers=headers, files=files)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/config")
def config():
    return jsonify({
        "locais": LOCAIS,
        "departamentos": DEPARTAMENTOS,
        "locais_item": LOCAIS_ITEM,
        "canais": CANAIS
    })

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("pdf")
        if not file:
            return jsonify({"erro": "Nenhum arquivo enviado"}), 400
        texto = extrair_texto_pdf(file)
        dados = extrair_dados_nf(texto)
        dados["filename"] = file.filename
        return jsonify(dados)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/criar_label", methods=["POST"])
def criar_label():
    try:
        data = request.json
        label_id = criar_label_monday(data["column_id"], data["label"])
        return jsonify({"id": label_id})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/enviar", methods=["POST"])
def enviar():
    try:
        data = request.form
        pdf_file = request.files.get("pdf")
        pdf_bytes = pdf_file.read() if pdf_file else None
        pdf_name = pdf_file.filename if pdf_file else "nota_fiscal.pdf"

        itens = json.loads(data.get("itens", "[]"))
        numero_nf = data.get("numero_nf", "")
        data_emissao = data.get("data_emissao", "")
        local = data.get("local", "")
        canal_compra = data.get("canal_compra", "")
        departamento = data.get("departamento", "")
        local_item = data.get("local_item", "")
        obs_local = data.get("obs_local", "")

        item_ids = []
        for item in itens:
            item_id = criar_item_monday(item, numero_nf, data_emissao, local, canal_compra, departamento, local_item, obs_local)
            item_ids.append(item_id)
            if pdf_bytes:
                anexar_pdf_monday(item_id, pdf_bytes, pdf_name)

        return jsonify({"sucesso": True, "total": len(item_ids)})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
