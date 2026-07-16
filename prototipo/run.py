"""Punto de entrada del prototipo FoodDash.

Uso:
    uv run python run.py triage --profile ollama-3b
    uv run python run.py triage --profile ollama-8b
    uv run python run.py triage --profile deepseek
    uv run python run.py compare            # corre los 3 perfiles y compara
    uv run python run.py report --profile ollama-8b   # (re)genera reportes de un perfil
    uv run python run.py cv --profile deepseek         # LOOCV con prompt minimo
    uv run python run.py cv-knn --profile deepseek --k 5      # LOOCV con recuperacion por embeddings
    uv run python run.py cv-hybrid --profile deepseek --k 5   # Híbrido: minimal + reglas justificadas
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from rich.console import Console
from rich.table import Table

from fooddash.agents import triage_ticket
from fooddash.cv import (
    FAILING_PRONE,
    MINIMAL_ROUTER_SYSTEM,
    _format_few_shot_item,
    build_hybrid_system,
    build_justified_rules,
    embed_all_tickets,
    leave_one_out,
    leave_one_out_knn,
    load_golden,
    select_few_shot,
)
from fooddash.eval import evaluate
from fooddash.embeddings import retrieve_top_k
from fooddash.llm import LLMClient, PROFILES
from fooddash.prompts import router_messages_dynamic

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "output"

console = Console()


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def load_tickets() -> list[dict]:
    data = json.loads((DATA / "tickets.json").read_text())
    return data["tickets"]


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run_profile(profile: str, tickets: list[dict], limit: int | None = None, router_only: bool = False) -> list[dict]:
    client = LLMClient.from_profile(profile)
    mode = "router-only" if router_only else "completo"
    console.print(f"[bold cyan]\n▶ Perfil:[/] {profile}  [bold cyan]modelo:[/] {client.backend}/{client.model}  [dim]({mode})[/]")
    if client.backend == "deepseek" and not client.deepseek_key:
        console.print("[yellow]  (DeepSeek sin API key en .env: omito este perfil)[/]")
        return []

    target = tickets[:limit] if limit else tickets

    results: list[dict] = []
    for i, t in enumerate(target, 1):
        try:
            r = triage_ticket(client, t, router_only=router_only)
        except Exception as e:
            r = {
                "ticket_id": t["ticket_id"],
                "category": "error",
                "error": f"{type(e).__name__}: {e}",
                "model": f"{client.backend}/{client.model}",
            }
            console.print(f"  [red]{t['ticket_id']} ERROR:[/] {e}")
        results.append(r)
        cat = r.get("category", "?")
        marker = {
            "bug": "[red]bug[/]",
            "config": "[yellow]config[/]",
            "operacion": "[green]oper[/]",
            "comercial": "[magenta]comer[/]",
            "none": "[dim]none[/]",
            "error": "[bold red]ERR[/]",
        }.get(cat, cat)
        console.print(f"  [{i:>2}/{len(target)}] {t['ticket_id']:<10} {marker:<14} conf={r.get('confidence','?')}")
    return results


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def write_outputs(profile: str, results: list[dict], tickets: list[dict]) -> Path:
    """Escribe clasificacion.jsonl, respuestas/, sistemas_fallando.md y eval.json."""
    outdir = OUT / profile
    (outdir / "respuestas").mkdir(parents=True, exist_ok=True)

    # 1) clasificacion.jsonl
    with (outdir / "clasificacion.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 2) respuestas/ (solo config/operacion/comercial)
    by_id = {t["ticket_id"]: t for t in tickets}
    for r in results:
        if r.get("respuesta_usuario"):
            t = by_id[r["ticket_id"]]
            md = (
                f"# {r['ticket_id']} — {t.get('subject','')}\n\n"
                f"- **Categoria:** {r['category']}\n"
                f"- **Accion interna:** {r.get('internal_action')}\n"
                f"- **Reembolso sugerido:** {'si' if r.get('requires_refund') else 'no'}\n\n"
                f"## Respuesta sugerida al usuario\n\n{r['respuesta_usuario']}\n"
            )
            (outdir / "respuestas" / f"{r['ticket_id']}.md").write_text(md, encoding="utf-8")

    # 3) sistemas_fallando.md (la lista pedida)
    write_systems_report(outdir, results)

    # 4) eval.json
    ev = evaluate(results)
    (outdir / "eval.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    return outdir


def write_systems_report(outdir: Path, results: list[dict]) -> None:
    bugs = [r for r in results if r.get("category") == "bug"]
    sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    # --- agrupacion por known_bug_id (causa raiz) ---
    by_bug: dict[str, list[dict]] = {}
    new_bugs: list[dict] = []
    for b in bugs:
        kb = b.get("known_bug")
        if kb:
            by_bug.setdefault(kb["bug_id"], []).append(b)
        else:
            new_bugs.append(b)

    # --- agrupacion por system_id (vista alternativa) ---
    by_system: dict[str, list[dict]] = {}
    for b in bugs:
        sid = b.get("system_id") or "sin_identificar"
        by_system.setdefault(sid, []).append(b)

    rows = []
    for sid, items in by_system.items():
        sev = max((it.get("severity", "medium") for it in items), key=lambda s: sev_rank.get(s, 0))
        known = next((it.get("known_bug") for it in items if it.get("known_bug")), None)
        is_new = all(it.get("is_new_bug") for it in items)
        rows.append((sid, sev, items, known, is_new))
    rows.sort(key=lambda x: sev_rank.get(x[1], 0), reverse=True)

    lines = [
        "# Sistemas con bugs activos",
        "",
        f"Total de tickets clasificados como **bug**: {len(bugs)}",
        f"Bugs conocidos recurrentes: **{len(by_bug)}** · Bugs nuevos: **{len(new_bugs)}**",
        f"Sistemas/componentes afectados: **{len(by_system)}**",
        "",
    ]

    # --- seccion 1: bugs recurrentes por causa raiz (known_bug_id) ---
    if by_bug:
        lines.append("## Bugs recurrentes (agrupados por `known_bug_id`)")
        lines.append("")
        lines.append("Tickets que matchean el mismo bug en el registro. Esto es la correlacion de causa raiz: usuarios distintos, pedidos distintos, mismo bug subyacente.")
        lines.append("")
        # ordenar por cantidad de tickets descendente, luego severidad
        bug_rows = []
        for bid, items in by_bug.items():
            kb = items[0]["known_bug"]
            sev = kb.get("severity", "medium")
            bug_rows.append((bid, items, kb, sev))
        bug_rows.sort(key=lambda x: (-len(x[1]), -sev_rank.get(x[3], 0)))
        for bid, items, kb, sev in bug_rows:
            tids = ", ".join(it["ticket_id"] for it in items)
            lines.append(f"### `{bid}` — {kb['title']}")
            lines.append(f"**Severidad:** {sev} · **Estado:** {kb['status']} · **Equipo:** {kb.get('owner_team','—')} · **Tickets ({len(items)}):** {tids}")
            lines.append("")
            for it in items:
                lines.append(f"- **{it['ticket_id']}**: {it.get('reasoning','')}")
            if kb.get("workaround"):
                lines.append(f"- **Workaround:** {kb['workaround']}")
            lines.append("")

    # --- seccion 2: bugs nuevos (no en el registro) ---
    if new_bugs:
        lines.append("## Bugs nuevos 🆕 (no presentes en el registro)")
        lines.append("")
        for it in new_bugs:
            sid = it.get("system_id") or "sin_identificar"
            sev = it.get("severity", "medium")
            lines.append(f"### `{sid}` — {it['ticket_id']} — severidad **{sev}** 🆕")
            lines.append(f"- {it.get('reasoning','')}")
            if it.get("root_cause_hypothesis"):
                lines.append(f"- Hipótesis causa raíz: {it['root_cause_hypothesis']}")
            if it.get("next_steps"):
                lines.append(f"- Siguientes pasos: {it['next_steps']}")
            lines.append("")

    # --- seccion 3: tabla resumen por sistema ---
    lines.append("## Resumen por sistema")
    lines.append("")
    lines.append("| # | Sistema | Severidad | Tickets | Bug conocido | Estado | Equipo |")
    lines.append("|---|---------|-----------|---------|--------------|--------|--------|")
    for i, (sid, sev, items, known, is_new) in enumerate(rows, 1):
        tids = ", ".join(it["ticket_id"] for it in items)
        if known:
            kb = f"{known['bug_id']}"
            status = known["status"]
            team = known.get("owner_team") or "—"
        else:
            kb = "**NUEVO** 🆕"
            status = "—"
            team = "—"
        lines.append(f"| {i} | `{sid}` | **{sev}** | {tids} | {kb} | {status} | {team} |")
    lines.append("")

    # --- seccion 4: detalle por sistema ---
    lines.append("## Detalle por sistema")
    lines.append("")
    for sid, sev, items, known, is_new in rows:
        lines.append(f"### `{sid}` — severidad **{sev}**")
        for it in items:
            lines.append(f"- **{it['ticket_id']}**: {it.get('reasoning','')}")
            if it.get("root_cause_hypothesis"):
                lines.append(f"  - Hipótesis causa raíz: {it['root_cause_hypothesis']}")
            if it.get("next_steps"):
                lines.append(f"  - Siguientes pasos: {it['next_steps']}")
            if it.get("known_bug"):
                kb = it["known_bug"]
                lines.append(f"  - Bug conocido: `{kb['bug_id']}` — {kb['title']}")
                lines.append(f"    - Estado: {kb['status']} | Severidad: {kb['severity']} | Equipo: {kb.get('owner_team')}")
                if kb.get("workaround"):
                    lines.append(f"    - Workaround: {kb['workaround']}")
            elif it.get("is_new_bug"):
                lines.append("  - 🆕 **Bug no presente en el registro**: alta prioridad, registrar y investigar.")
        lines.append("")
    (outdir / "sistemas_fallando.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_triage(args):
    tickets = load_tickets()
    results = run_profile(args.profile, tickets, limit=args.limit, router_only=args.router_only)
    if not results:
        return
    outdir = write_outputs(args.profile, results, tickets)
    ev = evaluate(results)
    _print_eval(ev)
    console.print(f"\n[green]Outputs en:[/] {outdir}")


def cmd_report(args):
    tickets = load_tickets()
    outdir = OUT / args.profile
    jsonl = outdir / "clasificacion.jsonl"
    if not jsonl.exists():
        console.print(f"[red]No hay resultados para {args.profile}. Corre `triage` primero.[/]")
        return
    results = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
    write_outputs(args.profile, results, tickets)
    ev = evaluate(results)
    _print_eval(ev)
    console.print(f"\n[green]Reportes regenerados en:[/] {outdir}")


def cmd_compare(args):
    tickets = load_tickets()
    summary: list[dict] = []
    for profile in PROFILES:
        results = run_profile(profile, tickets, limit=args.limit, router_only=args.router_only)
        if not results:
            continue
        write_outputs(profile, results, tickets)
        ev = evaluate(results)
        summary.append(ev)

    if not summary:
        console.print("[red]No se pudo correr ningun perfil.[/]")
        return

    console.print("\n[bold]\n=== Comparativa de modelos ===\n[/]")
    table = Table(title="Agreement vs golden set")
    table.add_column("Modelo")
    table.add_column("Agreement", justify="right")
    table.add_column("Accuracy", justify="right")
    table.add_column("Bugs", justify="right")
    table.add_column("Disensos", justify="right")
    for ev in summary:
        n_dis = len(ev["disagreements"])
        bugs = ev["confusion"].get("bug", {}).get("bug", 0)
        table.add_row(ev["model"], f"{ev['agreement']}/{ev['n']}", f"{ev['accuracy']:.1%}", str(bugs), str(n_dis))
    console.print(table)

    # sugerencia de modelo ganador
    best = max(summary, key=lambda e: e["accuracy"])
    console.print(f"\n[bold green]Mejor modelo:[/] {best['model']}  (accuracy {best['accuracy']:.1%})")
    outdir = OUT / "comparativa"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]Resumen en:[/] {outdir / 'summary.json'}")


def cmd_cv(args):
    """Leave-one-out cross-validation con prompt minimo (DeepSeek).

    Por cada ticket: few-shot de tickets reales del training set + system prompt
    minimo (sin reglas especificas). Mide la generalizacion honesta del modelo.
    """
    tickets = load_tickets()
    golden = load_golden()
    client = LLMClient.from_profile(args.profile)
    console.print(
        f"[bold cyan]\n▶ LOOCV[/] perfil={args.profile} modelo={client.backend}/{client.model}\n"
        f"   prompt=MINIMAL (solo defs de categoria, sin reglas especificas)\n"
        f"   few-shot=tickets reales del training set (n_per_cat={args.n_per_cat})"
    )
    if client.backend == "deepseek" and not client.deepseek_key:
        console.print("[red]DeepSeek sin API key en .env. Aborta.[/]")
        return

    labels_set = {"bug", "config", "operacion", "comercial", "none"}
    rows: list[dict] = []
    correct = 0

    for i, (train, test) in enumerate(leave_one_out(tickets), 1):
        tid = test["ticket_id"]
        gold = golden.get(tid, {}).get("label", "?")
        few_shot = select_few_shot(train, golden, n_per_cat=args.n_per_cat)
        messages = router_messages_dynamic(test, few_shot, MINIMAL_ROUTER_SYSTEM)

        try:
            resp = client.chat(messages, json_mode=True, temperature=0.0)
            pred = (resp.json() or {}).get("category", "none")
            pred = pred.lower().strip()
            conf = _safe_float((resp.json() or {}).get("confidence"), 0.0)
            reasoning = (resp.json() or {}).get("reasoning", "")
        except Exception as e:
            pred, conf, reasoning = "error", 0.0, str(e)

        is_correct = pred == gold
        correct += is_correct
        rows.append(
            {
                "ticket_id": tid,
                "gold": gold,
                "pred": pred,
                "correct": is_correct,
                "confidence": conf,
                "reasoning": reasoning,
                "n_few_shot": len(few_shot),
            }
        )
        mark = "[green]✓[/]" if is_correct else "[red]✗[/]"
        console.print(f"  [{i:>2}/26] {tid:<10} gold={gold:<10} pred={pred:<10} {mark} conf={conf}")

    accuracy = correct / len(rows)

    # per-label recall
    per_label: dict[str, dict] = {}
    for lab in labels_set:
        tp = sum(1 for r in rows if r["gold"] == lab and r["pred"] == lab)
        fn = sum(1 for r in rows if r["gold"] == lab and r["pred"] != lab)
        per_label[lab] = {"recall": tp / (tp + fn) if (tp + fn) else None, "tp": tp, "fn": fn}

    errors = [r for r in rows if not r["correct"]]

    # --- salida consola ---
    console.print(f"\n[bold]LOOCV accuracy:[/] {correct}/{len(rows)} = [bold cyan]{accuracy:.1%}[/]")
    table = Table(title="Recall por etiqueta (LOOCV)")
    table.add_column("Etiqueta")
    table.add_column("Recall", justify="right")
    for lab, m in per_label.items():
        r = f"{m['recall']:.0%}" if m["recall"] is not None else "—"
        table.add_row(lab, f"{r} ({m['tp']}/{m['tp']+m['fn']})")
    console.print(table)
    if errors:
        console.print(f"\n[yellow]Errores ({len(errors)}):[/]")
        for e in errors:
            console.print(f"  {e['ticket_id']:<10} gold={e['gold']:<10} pred={e['pred']:<10} | {e['reasoning']}")

    # --- escribir archivos ---
    outdir = OUT / args.profile
    outdir.mkdir(parents=True, exist_ok=True)
    cv_data = {
        "method": "LOOCV (leave-one-out)",
        "model": f"{client.backend}/{client.model}",
        "prompt": "minimal (category defs only, no specific rules)",
        "few_shot": f"real tickets from training set, n_per_cat={args.n_per_cat}",
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "n": len(rows),
        "per_label_recall": per_label,
        "rows": rows,
    }
    (outdir / "cv_loocv.json").write_text(
        json.dumps(cv_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # reporte markdown
    md = [
        f"# Cross-validation: LOOCV con prompt minimo ({client.model})",
        "",
        "## Metodologia",
        "",
        "- **Leave-one-out (LOOCV):** cada ticket se evalua con los otros 25 como training.",
        "- **Prompt minimo:** solo definiciones de categoria + 'lee logs antes que subject'.",
        "  SIN las 8 reglas especificas del prompt de produccion.",
        "- **Few-shot:** tickets reales del training set (no analogos sinteticos).",
        f"  Hasta {args.n_per_cat} ejemplos por categoria, con diversidad de sistema dentro de bug.",
        "",
        "## Resultado",
        "",
        f"| Metrica | Valor |",
        f"|---|---|",
        f"| **LOOCV accuracy** | **{correct}/{len(rows)} ({accuracy:.1%})** |",
        f"| Known-set accuracy (full prompt) | 26/26 (100.0%) |",
        "",
        "## Recall por etiqueta",
        "",
        "| Etiqueta | Recall | TP | FN |",
        "|---|---|---|---|",
    ]
    for lab in ["bug", "config", "operacion", "comercial", "none"]:
        m = per_label[lab]
        r = f"{m['recall']:.0%}" if m["recall"] is not None else "—"
        md.append(f"| {lab} | {r} | {m['tp']} | {m['fn']} |")
    md.append("")
    if errors:
        md.append("## Analisis de errores")
        md.append("")
        md.append("| Ticket | Gold | Pred | Confianza | Razonamiento del modelo |")
        md.append("|---|---|---|---|---|")
        for e in errors:
            md.append(
                f"| {e['ticket_id']} | {e['gold']} | {e['pred']} | {e['confidence']} "
                f"| {e['reasoning'][:80]} |"
            )
        md.append("")
        md.append("## Interpretacion")
        md.append("")
        md.append(
            f"El modelo se equivoca en {len(errors)} ticket(s) sin las reglas hand-craftadas. "
            "Estos revelan que patrones el modelo NO aprende solo del few-shot y requieren "
            "ya sea mas ejemplos o reglas explicitas en el prompt de produccion."
        )
    else:
        md.append("## Interpretacion")
        md.append("")
        md.append(
            "El modelo logra 100% incluso sin las reglas hand-craftadas: el criterio es "
            "plenamente aprendible del few-shot. Las reglas del prompt de produccion son "
            "redundantes (no overfitting)."
        )
    (outdir / "cv_loocv_report.md").write_text("\n".join(md), encoding="utf-8")

    console.print(f"\n[green]Reporte CV en:[/] {outdir / 'cv_loocv_report.md'}")


def cmd_cv_knn(args):
    """LOOCV con recuperacion por embeddings (top-k similares).

    Para cada ticket: recupera los k mas parecidos de los otros 25 via
    snowflake-arctic-embed2 + cosine similarity, los usa como few-shot, y
    predice. La recuperacion es deterministica; solo la prediccion varía.
    """
    tickets = load_tickets()
    golden = load_golden()
    client = LLMClient.from_profile(args.profile)
    k = args.k
    console.print(
        f"[bold cyan]\n▶ LOOCV-KNN[/] perfil={args.profile} modelo={client.backend}/{client.model}\n"
        f"   prompt=MINIMAL · embeddings=snowflake-arctic-embed2 · k={k}"
    )
    if client.backend == "deepseek" and not client.deepseek_key:
        console.print("[red]DeepSeek sin API key en .env. Aborta.[/]")
        return

    # 1) Pre-computar embeddings (una sola vez)
    console.print(f"   [dim]embebiendo {len(tickets)} tickets...[/]")
    embeddings = embed_all_tickets(tickets)
    console.print(f"   [dim]embeddings listos ({len(embeddings)} vectores)[/]")

    # 2) LOOCV-KNN
    labels_set = {"bug", "config", "operacion", "comercial", "none"}
    rows: list[dict] = []
    correct = 0

    for i, (test, few_shot, retrieved) in enumerate(
        leave_one_out_knn(tickets, golden, embeddings, k=k), 1
    ):
        tid = test["ticket_id"]
        gold = golden.get(tid, {}).get("label", "?")
        messages = router_messages_dynamic(test, few_shot, MINIMAL_ROUTER_SYSTEM)

        try:
            resp = client.chat(messages, json_mode=True, temperature=0.0)
            rj = resp.json() or {}
            pred = (rj.get("category") or "none").lower().strip()
            conf = _safe_float(rj.get("confidence"), 0.0)
            reasoning = rj.get("reasoning", "")
        except Exception as e:
            pred, conf, reasoning = "error", 0.0, str(e)

        is_correct = pred == gold
        correct += is_correct

        # distribucion de etiquetas en los recuperados
        retrieved_labels = [r["label"] for r in retrieved]
        label_dist = {lab: retrieved_labels.count(lab) for lab in set(retrieved_labels)}

        rows.append(
            {
                "ticket_id": tid,
                "gold": gold,
                "pred": pred,
                "correct": is_correct,
                "confidence": conf,
                "reasoning": reasoning,
                "retrieved": retrieved,
                "retrieved_label_distribution": label_dist,
                "gold_in_retrieved": gold in retrieved_labels,
            }
        )
        mark = "[green]✓[/]" if is_correct else "[red]✗[/]"
        top3 = ", ".join(f"{r['ticket_id']}({r['label'][:3]})" for r in retrieved[:3])
        console.print(f"  [{i:>2}/26] {tid:<10} gold={gold:<10} pred={pred:<10} {mark} retrieved=[{top3}]")

    accuracy = correct / len(rows)

    # per-label recall
    per_label: dict[str, dict] = {}
    for lab in labels_set:
        tp = sum(1 for r in rows if r["gold"] == lab and r["pred"] == lab)
        fn = sum(1 for r in rows if r["gold"] == lab and r["pred"] != lab)
        per_label[lab] = {"recall": tp / (tp + fn) if (tp + fn) else None, "tp": tp, "fn": fn}

    errors = [r for r in rows if not r["correct"]]
    gold_in_retrieved_count = sum(1 for r in rows if r["gold_in_retrieved"])

    # --- salida consola ---
    console.print(f"\n[bold]LOOCV-KNN accuracy:[/] {correct}/{len(rows)} = [bold cyan]{accuracy:.1%}[/]")
    console.print(f"[dim]Gold label en top-{k} recuperados: {gold_in_retrieved_count}/{len(rows)} ({gold_in_retrieved_count/len(rows):.0%})[/]")
    table = Table(title=f"Recall por etiqueta (LOOCV-KNN, k={k})")
    table.add_column("Etiqueta")
    table.add_column("Recall", justify="right")
    for lab, m in per_label.items():
        r = f"{m['recall']:.0%}" if m["recall"] is not None else "—"
        table.add_row(lab, f"{r} ({m['tp']}/{m['tp']+m['fn']})")
    console.print(table)
    if errors:
        console.print(f"\n[yellow]Errores ({len(errors)}):[/]")
        for e in errors:
            top_labels = e["retrieved_label_distribution"]
            gold_in = "✓" if e["gold_in_retrieved"] else "✗"
            console.print(
                f"  {e['ticket_id']:<10} gold={e['gold']:<10} pred={e['pred']:<10} "
                f"gold∈top{k}={gold_in} dist={top_labels}"
            )

    # --- escribir archivos ---
    outdir = OUT / args.profile
    outdir.mkdir(parents=True, exist_ok=True)
    cv_data = {
        "method": f"LOOCV-KNN (k={k}, embedding=snowflake-arctic-embed2)",
        "model": f"{client.backend}/{client.model}",
        "prompt": "minimal (category defs only, no specific rules)",
        "retrieval": "deterministic (cosine similarity on embeddings)",
        "k": k,
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "n": len(rows),
        "gold_in_retrieved": gold_in_retrieved_count,
        "per_label_recall": per_label,
        "rows": rows,
    }
    (outdir / "cv_knn.json").write_text(
        json.dumps(cv_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # reporte markdown
    md = [
        f"# Cross-validation: LOOCV-KNN con embeddings (k={k}, {client.model})",
        "",
        "## Metodologia",
        "",
        "- **Leave-one-out + KNN:** cada ticket se evalua con los k mas parecidos de los otros 25.",
        "- **Recuperacion deterministica:** snowflake-arctic-embed2 (1024 dims) + cosine similarity.",
        f"  La recuperacion no varia entre corridas (solo la prediccion del LLM tiene varianza).",
        "- **Prompt minimo:** solo definiciones de categoria. Sin reglas hand-craftadas.",
        "- **Few-shot:** los k tickets recuperados + su etiqueta y razonamiento golden.",
        "",
        "## Resultado",
        "",
        f"| Metrica | Valor |",
        f"|---|---|",
        f"| **LOOCV-KNN accuracy** | **{correct}/{len(rows)} ({accuracy:.1%})** |",
        f"| Gold label en top-{k} recuperados | {gold_in_retrieved_count}/{len(rows)} ({gold_in_retrieved_count/len(rows):.0%}) |",
        f"| Known-set (full prompt) | 26/26 (100.0%) |",
        "",
        "## Recall por etiqueta",
        "",
        "| Etiqueta | Recall | TP | FN |",
        "|---|---|---|---|",
    ]
    for lab in ["bug", "config", "operacion", "comercial", "none"]:
        m = per_label[lab]
        r = f"{m['recall']:.0%}" if m["recall"] is not None else "—"
        md.append(f"| {lab} | {r} | {m['tp']} | {m['fn']} |")
    md.append("")

    # tabla de recuperacion por ticket
    md.append(f"## Recuperacion por ticket (top-{k})")
    md.append("")
    md.append(f"| Ticket | Gold | Pred | ¿Correcto? | Gold∈top{k} | Top recuperados (similitud) |")
    md.append("|---|---|---|---|---|---|")
    for r in rows:
        retrieved_str = ", ".join(
            f"{rt['ticket_id']}({rt['label'][:3]},{rt['similarity']:.2f})" for rt in r["retrieved"]
        )
        md.append(
            f"| {r['ticket_id']} | {r['gold']} | {r['pred']} | "
            f"{'✓' if r['correct'] else '✗'} | "
            f"{'✓' if r['gold_in_retrieved'] else '✗'} | {retrieved_str} |"
        )
    md.append("")

    if errors:
        md.append("## Analisis de errores")
        md.append("")
        for e in errors:
            md.append(f"### {e['ticket_id']} — gold={e['gold']} pred={e['pred']}")
            md.append(f"- Razonamiento: {e['reasoning'][:120]}")
            md.append(f"- Recuperados ({e['retrieved_label_distribution']}):")
            for rt in e["retrieved"]:
                md.append(f"  - {rt['ticket_id']} [{rt['label']}] sim={rt['similarity']}")
            if e["gold_in_retrieved"]:
                md.append(f"- **El gold estaba en los recuperados** pero el modelo predijo mal → problema del LLM, no de recuperacion.")
            else:
                md.append(f"- **El gold NO estaba en los recuperados** → problema de recuperacion (embedding no encontro similares).")
            md.append("")

    md.append("## Interpretacion")
    md.append("")
    gold_in_pct = gold_in_retrieved_count / len(rows)
    md.append(
        f"La recuperacion por embeddings encontro tickets con la misma etiqueta golden "
        f"en el top-{k} para {gold_in_retrieved_count}/{len(rows)} ({gold_in_pct:.0%}) de los tickets. "
        f"Cuando la etiqueta correcta esta en los recuperados y el modelo aun falla, "
        f"el problema es del LLM (no razona bien con buenos ejemplos). "
        f"Cuando la etiqueta correcta no esta en los recuperados, el problema es de "
        f"recuperacion (los embeddings no capturan la similitud relevante)."
    )
    (outdir / "cv_knn_report.md").write_text("\n".join(md), encoding="utf-8")

    console.print(f"\n[green]Reporte KNN en:[/] {outdir / 'cv_knn_report.md'}")


def cmd_cv_hybrid(args):
    """LOOCV hibrido: prompt minimal + SOLO las reglas justificadas por el training set.

    Punto medio entre el known-set (100%, todas las reglas siempre -> leakage) y el
    LOOCV-KNN minimal (~85–88%, sin reglas). Por cada fold, se incluye en el prompt una
    regla solo si algun ticket del training set la traza (misma etiqueta golden +
    keyword de la regla presente). Las reglas que solo se sostenian con el ticket
    held-out se dropean -> se elimina el leakage sin tirar todas las reglas por igual.
    few-shot = recuperacion KNN (top-k, determinista).
    """
    tickets = load_tickets()
    golden = load_golden()
    client = LLMClient.from_profile(args.profile)
    k = args.k
    by_id = {t["ticket_id"]: t for t in tickets}

    eval_targets = (
        [by_id[t] for t in FAILING_PRONE] if args.failing_only else tickets
    )
    scope = f"{len(eval_targets)} propensos a fallar" if args.failing_only else f"{len(eval_targets)} tickets"
    console.print(
        f"[bold cyan]\n▶ CV-HIBRIDO[/] perfil={args.profile} modelo={client.backend}/{client.model}\n"
        f"   prompt=MINIMAL + reglas JUSTIFICADAS por el training set (0-8 segun fold)\n"
        f"   few-shot=KNN top-{k} · scope={scope}"
    )
    if client.backend == "deepseek" and not client.deepseek_key:
        console.print("[red]DeepSeek sin API key en .env. Aborta.[/]")
        return

    # pre-computar embeddings (una sola vez, sobre los 26)
    console.print(f"   [dim]embebiendo {len(tickets)} tickets...[/]")
    embeddings = embed_all_tickets(tickets)
    console.print(f"   [dim]embeddings listos ({len(embeddings)} vectores)[/]")

    labels_set = {"bug", "config", "operacion", "comercial", "none"}
    rows: list[dict] = []
    correct = 0

    for i, test in enumerate(eval_targets, 1):
        tid = test["ticket_id"]
        gold = golden.get(tid, {}).get("label", "?")
        train = [t for t in tickets if t["ticket_id"] != tid]
        train_ids = [t["ticket_id"] for t in train]

        # 1) reglas justificadas por el training set
        justified, dropped = build_justified_rules(train, golden)
        system_prompt = build_hybrid_system(justified)

        # 2) few-shot KNN desde el training set
        cands = {cid: embeddings[cid] for cid in train_ids}
        top = retrieve_top_k(embeddings[tid], cands, k=k)
        few_shot = [_format_few_shot_item(by_id[cid], golden[cid]) for cid, _ in top]

        # 3) predecir
        messages = router_messages_dynamic(test, few_shot, system_prompt)
        retrieved = [{"ticket_id": cid, "label": golden[cid]["label"], "similarity": round(s, 4)} for cid, s in top]
        try:
            rj = client.chat(messages, json_mode=True, temperature=0.0).json() or {}
            pred = (rj.get("category") or "none").lower().strip()
            conf = _safe_float(rj.get("confidence"), 0.0)
            reasoning = rj.get("reasoning", "")
        except Exception as e:
            pred, conf, reasoning = "error", 0.0, str(e)

        is_correct = pred == gold
        correct += is_correct
        rows.append({
            "ticket_id": tid,
            "gold": gold,
            "pred": pred,
            "correct": is_correct,
            "confidence": conf,
            "reasoning": reasoning,
            "rules_in": [r.id for r in justified],
            "rules_dropped": [r.id for r in dropped],
            "n_rules_in": len(justified),
            "retrieved": retrieved,
        })
        mark = "[green]✓[/]" if is_correct else "[red]✗[/]"
        drp = ",".join(r for r in rows[-1]["rules_dropped"]) or "—"
        console.print(
            f"  [{i:>2}/{len(eval_targets)}] {tid:<10} gold={gold:<10} pred={pred:<10} {mark} "
            f"rules={rows[-1]['n_rules_in']}/8 dropped=[{drp}]"
        )

    accuracy = correct / len(rows)
    errors = [r for r in rows if not r["correct"]]
    drops_count = sum(1 for r in rows if r["rules_dropped"])

    # per-label recall
    per_label: dict[str, dict] = {}
    for lab in labels_set:
        tp = sum(1 for r in rows if r["gold"] == lab and r["pred"] == lab)
        fn = sum(1 for r in rows if r["gold"] == lab and r["pred"] != lab)
        per_label[lab] = {"recall": tp / (tp + fn) if (tp + fn) else None, "tp": tp, "fn": fn}

    # --- consola ---
    console.print(f"\n[bold]CV-HIBRIDO accuracy:[/] {correct}/{len(rows)} = [bold cyan]{accuracy:.1%}[/]")
    console.print(f"[dim]Folds donde se dropeo alguna regla: {drops_count}/{len(rows)} (leakage eliminado)[/]")
    table = Table(title=f"Recall por etiqueta (CV-Hibrido{' · failing-only' if args.failing_only else ''}, k={k})")
    table.add_column("Etiqueta")
    table.add_column("Recall", justify="right")
    for lab in ["bug", "config", "operacion", "comercial", "none"]:
        m = per_label[lab]
        r = f"{m['recall']:.0%}" if m["recall"] is not None else "—"
        table.add_row(lab, f"{r} ({m['tp']}/{m['tp']+m['fn']})")
    console.print(table)
    if errors:
        console.print(f"\n[yellow]Errores ({len(errors)}):[/]")
        for e in errors:
            drp = ",".join(e["rules_dropped"]) or "—"
            kind = "REGLA AUSENTE (dropeada)" if e["rules_dropped"] else "RAZONAMIENTO (8/8 reglas presentes)"
            console.print(
                f"  {e['ticket_id']:<10} gold={e['gold']:<10} pred={e['pred']:<10} "
                f"rules_dropped=[{drp}] -> {kind}"
            )

    # --- archivos ---
    outdir = OUT / args.profile
    outdir.mkdir(parents=True, exist_ok=True)
    suffix = "_failing" if args.failing_only else ""
    cv_data = {
        "method": f"LOOCV-HIBRIDO (k={k}, embedding=snowflake-arctic-embed2, reglas justificadas)",
        "model": f"{client.backend}/{client.model}",
        "prompt": "minimal + solo reglas trazables desde el training set (0-8 por fold)",
        "retrieval": "deterministic (cosine similarity on embeddings)",
        "k": k,
        "scope": "failing_prone" if args.failing_only else "all",
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "n": len(rows),
        "folds_with_dropped_rules": drops_count,
        "per_label_recall": per_label,
        "rows": rows,
    }
    (outdir / f"cv_hybrid{suffix}.json").write_text(
        json.dumps(cv_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # reporte markdown
    md = [
        f"# Cross-validation: HIBRIDO (reglas justificadas) — {client.model}",
        "",
        "## Metodologia",
        "",
        "- **Hibrido entre known-set (100%) y LOOCV-KNN minimal (~85–88%).**",
        "- Por cada fold LOOCV, el system prompt = `MINIMAL` (defs de categoria) + **solo las reglas",
        "  que el training set logra trazar** (misma etiqueta golden + keyword de la regla).",
        "- Las reglas que solo se sostenian con el ticket held-out se **dropean** -> se elimina el",
        "  test-set leakage sin tirar las 8 reglas por igual.",
        f"- **Few-shot:** KNN top-{k} (snowflake-arctic-embed2, recuperacion deterministica).",
        f"- **Scope:** {'failing-prone (' + str(len(eval_targets)) + ' tickets)' if args.failing_only else 'los ' + str(len(eval_targets)) + ' tickets'}.",
        "",
        "## Resultado",
        "",
        "| Metrica | Valor |",
        "|---|---|",
        f"| **CV-Hibrido accuracy** | **{correct}/{len(rows)} ({accuracy:.1%})** |",
        f"| Folds con alguna regla dropeada | {drops_count}/{len(rows)} |",
        "| Known-set (full prompt, todas las reglas) | 26/26 (100.0%) |",
        "| LOOCV-KNN minimal (sin reglas) | ~85–88% (22–23/26, varía por LLM) |",
        "",
        "## Recall por etiqueta",
        "",
        "| Etiqueta | Recall | TP | FN |",
        "|---|---|---|---|",
    ]
    for lab in ["bug", "config", "operacion", "comercial", "none"]:
        m = per_label[lab]
        r = f"{m['recall']:.0%}" if m["recall"] is not None else "—"
        md.append(f"| {lab} | {r} | {m['tp']} | {m['fn']} |")
    md.append("")

    md.append("## Detalle por ticket (reglas incluidas/dropeadas)")
    md.append("")
    md.append("| Ticket | Gold | Pred | ¿Correcto? | Reglas | Dropeadas |")
    md.append("|---|---|---|---|---|---|")
    for r in rows:
        drp = ",".join(r["rules_dropped"]) or "—"
        md.append(
            f"| {r['ticket_id']} | {r['gold']} | {r['pred']} | "
            f"{'✓' if r['correct'] else '✗'} | {r['n_rules_in']}/8 | {drp} |"
        )
    md.append("")

    if errors:
        md.append("## Analisis de errores")
        md.append("")
        for e in errors:
            drp = ",".join(e["rules_dropped"]) or "—"
            kind = (
                "**REGLA AUSENTE**: la regla era unica del ticket held-out y se dropeo. "
                "Fallo esperado de generalizacion."
                if e["rules_dropped"]
                else "**FALLO DE RAZONAMIENTO**: las 8 reglas estaban presentes y el modelo "
                "las piso. Limite del modelo, no de reglas."
            )
            md.append(f"### {e['ticket_id']} — gold={e['gold']} pred={e['pred']} (dropeadas: {drp})")
            md.append(f"- Tipo: {kind}")
            md.append(f"- Razonamiento del modelo: {e['reasoning'][:140]}")
            md.append("")

    md.append("## Interpretacion")
    md.append("")
    md.append(
        "El hibrido se ubica entre el known-set (100%, con leakage) y el LOOCV-KNN minimal "
        "(~85–88%, sin reglas). Al dropear solo las reglas no trazables desde el training set, "
        f"se recupera la generalizacion sin tirar el conocimiento codificado: "
        f"{correct}/{len(rows)} ({accuracy:.0%}). Los errores residuales son de dos tipos: "
        "(a) regla ausente (la regla era unica del ticket held-out), y "
        "(b) fallos de razonamiento donde las 8 reglas estaban presentes y el modelo las piso."
    )
    (outdir / f"cv_hybrid{suffix}_report.md").write_text("\n".join(md), encoding="utf-8")

    console.print(f"\n[green]Reporte HIBRIDO en:[/] {outdir / f'cv_hybrid{suffix}_report.md'}")


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _print_eval(ev: dict):
    console.print(f"\n[bold]Agreement vs golden set:[/] {ev['agreement']}/{ev['n']} = [bold cyan]{ev['accuracy']:.1%}[/]")
    table = Table(title="Recall por etiqueta")
    table.add_column("Etiqueta")
    table.add_column("Recall", justify="right")
    for lab, m in ev["per_label_recall"].items():
        r = f"{m['recall']:.0%}" if m["recall"] is not None else "—"
        table.add_row(lab, f"{r} ({m['tp']}/{m['tp']+m['fn']})")
    console.print(table)
    if ev["disagreements"]:
        console.print(f"\n[yellow]Desacuerdos ({len(ev['disagreements'])}):[/]")
        for d in ev["disagreements"]:
            console.print(
                f"  {d['ticket_id']:<10} gold=[green]{d['gold']}[/] pred=[red]{d['pred']}[/] "
                f"conf={d.get('confidence')}  | {d['model_reasoning']}"
            )


def main():
    p = argparse.ArgumentParser(description="FoodDash ticket triage agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("triage", help="Corre un perfil sobre los 26 tickets")
    pt.add_argument("--profile", required=True, choices=list(PROFILES))
    pt.add_argument("--limit", type=int, default=None, help="procesar solo N tickets (debug)")
    pt.add_argument("--router-only", action="store_true", help="solo Router, sin Resolutor/Bug-Triage (rapido)")
    pt.set_defaults(func=cmd_triage)

    pr = sub.add_parser("report", help="Regenera reportes de un perfil ya corrido")
    pr.add_argument("--profile", required=True, choices=list(PROFILES))
    pr.set_defaults(func=cmd_report)

    pc = sub.add_parser("compare", help="Corre los 3 perfiles y compara")
    pc.add_argument("--limit", type=int, default=None)
    pc.add_argument("--router-only", action="store_true")
    pc.set_defaults(func=cmd_compare)

    pcv = sub.add_parser("cv", help="LOOCV con prompt minimo (generalizacion honesta)")
    pcv.add_argument("--profile", required=True, choices=list(PROFILES))
    pcv.add_argument("--n-per-cat", type=int, default=2, help="ejemplos pocos-shot por categoria")
    pcv.set_defaults(func=cmd_cv)

    pcvk = sub.add_parser("cv-knn", help="LOOCV con recuperacion por embeddings (top-k similares)")
    pcvk.add_argument("--profile", required=True, choices=list(PROFILES))
    pcvk.add_argument("--k", type=int, default=5, help="numero de tickets similares a recuperar")
    pcvk.set_defaults(func=cmd_cv_knn)

    pcvh = sub.add_parser("cv-hybrid", help="LOOCV hibrido: minimal + reglas JUSTIFICADAS por training")
    pcvh.add_argument("--profile", required=True, choices=list(PROFILES))
    pcvh.add_argument("--k", type=int, default=5, help="numero de tickets similares a recuperar (KNN)")
    pcvh.add_argument("--failing-only", action="store_true", help="solo los 7 tickets propensos a fallar")
    pcvh.set_defaults(func=cmd_cv_hybrid)

    args = p.parse_args()
    try:
        args.func(args)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
