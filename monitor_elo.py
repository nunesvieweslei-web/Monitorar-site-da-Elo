#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robô de monitoramento do site da Elo (https://www.elo.com.br/).
 
O que ele faz:
  1. Baixa a página.
  2. Extrai o texto visível e a lista de imagens/links relevantes.
     (O site usa nomes de arquivo "com hash" — quando o conteúdo muda,
      o nome do arquivo muda também. Isso é um ótimo sinal de mudança.)
  3. Compara com a última versão salva (arquivo snapshot.json).
  4. Se mudou, escreve um resumo do que foi ajustado e (opcionalmente)
     manda um e-mail pra você.
 
Como rodar:
    python3 monitor_elo.py
 
Para receber e-mail, defina estas variáveis de ambiente antes de rodar:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO
(se elas não existirem, o robô só mostra o resumo na tela / no log)
"""
 
import os
import re
import sys
import json
import smtplib
import difflib
from datetime import datetime
from email.message import EmailMessage
 
import requests
from bs4 import BeautifulSoup
 
URL = "https://www.elo.com.br/ofertas/"
SNAPSHOT_FILE = "snapshot.json"
TIMEOUT = 30
 
 
def baixar_pagina(url: str) -> str:
    """Baixa o HTML da página. Usa um User-Agent de navegador comum."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text
 
 
def extrair_conteudo(html: str) -> dict:
    """Transforma o HTML em duas coisas comparáveis: texto e ativos (imagens/links)."""
    soup = BeautifulSoup(html, "html.parser")
 
    # Remove o que não é conteúdo visível
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
 
    # Texto visível, uma "frase" por linha, sem linhas vazias repetidas
    texto = soup.get_text(separator="\n")
    linhas = [re.sub(r"\s+", " ", l).strip() for l in texto.splitlines()]
    linhas = [l for l in linhas if l]
 
    # Ativos: imagens, vídeos e links. Os nomes "com hash" denunciam mudanças.
    ativos = set()
    for el in soup.find_all(["img", "source"]):
        src = el.get("src") or el.get("data-src")
        if src:
            ativos.add(src.strip())
    for a in soup.find_all("a", href=True):
        ativos.add(a["href"].strip())
 
    return {"linhas": linhas, "ativos": sorted(ativos)}
 
 
def carregar_snapshot() -> dict | None:
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
 
 
def salvar_snapshot(conteudo: dict) -> None:
    dados = {"timestamp": datetime.now().isoformat(timespec="seconds"), **conteudo}
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
 
 
def comparar(antigo: dict, novo: dict) -> str:
    """Gera um resumo legível das diferenças. Retorna '' se nada mudou."""
    partes = []
 
    # Diferenças de texto
    diff = list(
        difflib.unified_diff(
            antigo["linhas"], novo["linhas"], lineterm="", n=0
        )
    )
    adicionadas = [l[1:].strip() for l in diff if l.startswith("+") and not l.startswith("+++")]
    removidas = [l[1:].strip() for l in diff if l.startswith("-") and not l.startswith("---")]
 
    if adicionadas:
        partes.append("📌 TEXTOS NOVOS / ALTERADOS:")
        partes += [f"   + {l}" for l in adicionadas]
    if removidas:
        partes.append("🗑️  TEXTOS QUE SUMIRAM:")
        partes += [f"   - {l}" for l in removidas]
 
    # Diferenças de imagens/links
    a_antigos = set(antigo["ativos"])
    a_novos = set(novo["ativos"])
    novos_ativos = sorted(a_novos - a_antigos)
    ativos_removidos = sorted(a_antigos - a_novos)
 
    if novos_ativos:
        partes.append("🖼️  IMAGENS / LINKS NOVOS:")
        partes += [f"   + {a}" for a in novos_ativos]
    if ativos_removidos:
        partes.append("❌ IMAGENS / LINKS REMOVIDOS:")
        partes += [f"   - {a}" for a in ativos_removidos]
 
    return "\n".join(partes)
 
 
def enviar_email(resumo: str) -> None:
    """Envia o resumo por e-mail, se as variáveis de ambiente estiverem definidas."""
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    senha = os.environ.get("SMTP_PASS")
    destino = os.environ.get("EMAIL_TO")
    porta = int(os.environ.get("SMTP_PORT", "587"))
 
    if not all([host, user, senha, destino]):
        print("(E-mail não configurado — pulando envio. Resumo mostrado acima.)")
        return
 
    msg = EmailMessage()
    msg["Subject"] = f"[Elo] O site mudou — {datetime.now():%d/%m/%Y %H:%M}"
    msg["From"] = user
    msg["To"] = destino
    msg.set_content(f"Detectei mudanças em {URL}:\n\n{resumo}")
 
    with smtplib.SMTP(host, porta) as servidor:
        servidor.starttls()
        servidor.login(user, senha)
        servidor.send_message(msg)
    print(f"E-mail enviado para {destino}.")
 
 
def main() -> None:
    try:
        html = baixar_pagina(URL)
    except Exception as e:
        print(f"Erro ao baixar a página: {e}", file=sys.stderr)
        sys.exit(1)
 
    novo = extrair_conteudo(html)
    antigo = carregar_snapshot()
 
    if antigo is None:
        salvar_snapshot(novo)
        print("Primeira execução: foto inicial do site salva. "
              "A partir de agora, vou comparar com esta versão.")
        return
 
    resumo = comparar(antigo, novo)
    if resumo:
        print(f"=== MUDANÇAS DETECTADAS em {datetime.now():%d/%m/%Y %H:%M} ===\n")
        print(resumo)
        enviar_email(resumo)
        salvar_snapshot(novo)  # atualiza a referência
    else:
        print(f"Nada mudou ({datetime.now():%d/%m/%Y %H:%M}).")
 
 
if __name__ == "__main__":
    main()
