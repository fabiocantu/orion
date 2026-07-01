from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import boards as boards_module
from .boards import board_grade_summary, board_partial_grade, get_exam_board, get_minutes, list_board_members, list_exam_criteria, list_grades
from .database import PDF_DIR, execute, query
from .timezone import now_local
from .utils import format_date_br, get_answers, get_record, get_student_context_by_session, list_criteria


LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "logo.png"


def calculate_plan_occupation_grade(partial_1: object, partial_2: object, board_average: object) -> float | None:
    if hasattr(boards_module, "calculate_plan_occupation_grade"):
        return boards_module.calculate_plan_occupation_grade(partial_1, partial_2, board_average)
    if board_average is None:
        return None

    def as_float(value: object) -> float:
        if value is None:
            return 0.0
        text = str(value).strip().replace(",", ".")
        if not text or text.lower() in {"nan", "none", "null"}:
            return 0.0
        return float(text)

    return round(as_float(partial_1) * 0.1 + as_float(partial_2) * 0.2 + as_float(board_average) * 0.7, 2)


def generate_record_pdf(session_id: int) -> Path:
    context = get_student_context_by_session(session_id)
    record = get_record(session_id)
    if not context or not record:
        raise ValueError("Ficha não encontrada para gerar PDF.")
    criteria_rows = list_criteria(context["tfg_stage"], context["phase"])
    answers = get_answers(record["id"])

    filename = f"ficha_tfg_sessao_{session_id}_{now_local().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = PDF_DIR / filename
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.5 * cm, leftMargin=1.5 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    styles = _styles()
    story = []

    header = Table(
        [[_institutional_logo(styles), Paragraph("<b>Ficha de Assessoria de TFG</b><br/>Centro Universitário Mater Dei<br/>Curso de Arquitetura e Urbanismo", styles["HeadingClean"])]],
        colWidths=[4 * cm, 13 * cm],
    )
    header.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.5, colors.grey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.extend([header, Spacer(1, 10)])

    info = [
        ["Etapa", _p(context["tfg_stage"], styles["SmallWrap"]), "Fase", _p(context["phase"], styles["SmallWrap"])],
        ["Assessoria", _p(str(context["session_number"]), styles["SmallWrap"]), "Orientador", _p(context["advisor_name"], styles["SmallWrap"])],
        ["Aluno", _p(context["name"], styles["SmallWrap"]), "E-mail", _p(context["email"] or "", styles["SmallWrap"])],
        ["Tema", _p(context["theme"], styles["SmallWrap"]), "Data prevista", _p(format_date_br(context["planned_date"]), styles["SmallWrap"])],
        ["Data realizada", _p(format_date_br(context["actual_date"], ""), styles["SmallWrap"]), "Geração", _p(now_local().strftime("%d/%m/%Y %H:%M"), styles["SmallWrap"])],
    ]
    story.append(_table(info, [3 * cm, 6.8 * cm, 3 * cm, 4.2 * cm]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Critérios avaliados</b>", styles["Normal"]))
    criteria_data = [["Critério", "Descrição", "Avaliação", "Comentário"]]
    for criterion in criteria_rows:
        answer = answers.get(criterion["id"], {})
        criteria_data.append([
            Paragraph(criterion["group_name"], styles["SmallWrap"]),
            Paragraph(criterion["description"], styles["SmallWrap"]),
            Paragraph(answer.get("answer", ""), styles["SmallWrap"]),
            Paragraph(answer.get("comment") or "", styles["SmallWrap"]),
        ])
    story.append(_table(criteria_data, [3.4 * cm, 6.7 * cm, 3.2 * cm, 3.7 * cm], header=True))
    story.append(Spacer(1, 10))

    narrative = [
        [Paragraph("Situação atual e recomendações gerais", styles["SmallWrap"]), Paragraph(record["general_notes"] or "", styles["SmallWrap"])],
        [Paragraph("Encaminhamentos", styles["SmallWrap"]), Paragraph(record["referrals"] or "", styles["SmallWrap"])],
        [Paragraph("Pendências", styles["SmallWrap"]), Paragraph(record["pending_issues"] or "", styles["SmallWrap"])],
        [Paragraph("Avaliação final", styles["SmallWrap"]), Paragraph(record["final_evaluation"] or "", styles["SmallWrap"])],
        [Paragraph("Comentário geral", styles["SmallWrap"]), Paragraph(record["final_comment"] or "", styles["SmallWrap"])],
    ]
    story.append(_table(narrative, [4.8 * cm, 12.2 * cm]))
    doc.build(story)
    execute("INSERT INTO pdf_exports (record_id, file_path) VALUES (?, ?)", (record["id"], str(path)))
    return path


def generate_board_pdf(board_id: int) -> Path:
    board_row = get_exam_board(board_id)
    board = dict(board_row) if board_row else None
    if not board:
        raise ValueError("Banca não encontrada para gerar PDF.")

    members = [dict(row) for row in list_board_members(board_id)]
    criteria_rows = [dict(row) for row in list_exam_criteria(board["stage"])]
    grades = [dict(row) for row in list_grades(board_id)]
    minutes_row = get_minutes(board_id)
    minutes = dict(minutes_row) if minutes_row else None
    summary = [dict(row) for row in board_grade_summary(board_id)]
    final_grade_row = board_partial_grade(board_id)
    final_grade = dict(final_grade_row) if final_grade_row else {"average_grade": None, "grades_count": 0}

    filename = f"relatorio_banca_{board_id}_{now_local().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = PDF_DIR / filename
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.5 * cm, leftMargin=1.5 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    styles = _styles()
    story = []

    header = Table(
        [[_institutional_logo(styles), Paragraph("<b>Relatório de Banca de TFG</b><br/>Centro Universitário Mater Dei<br/>Curso de Arquitetura e Urbanismo", styles["HeadingClean"])]],
        colWidths=[4 * cm, 13 * cm],
    )
    header.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.5, colors.grey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.extend([header, Spacer(1, 10)])

    scheduled = format_date_br(board["scheduled_date"])
    if board["scheduled_time"]:
        scheduled = f"{scheduled} {board['scheduled_time']}"
    info = [
        ["Aluno", _p(board["student_name"], styles["SmallWrap"]), "Etapa", _p(board["stage"], styles["SmallWrap"])],
        ["TFG", _p(board["tfg_stage"], styles["SmallWrap"]), "Data da banca", _p(scheduled, styles["SmallWrap"])],
        ["Tema", _p(board["theme"], styles["SmallWrap"]), "Local", _p(board["location"] or "", styles["SmallWrap"])],
        ["Status", _p(board["status"], styles["SmallWrap"]), "Geração", _p(now_local().strftime("%d/%m/%Y %H:%M"), styles["SmallWrap"])],
    ]
    story.append(_table(info, [3 * cm, 6.8 * cm, 3 * cm, 4.2 * cm]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Composição da banca</b>", styles["Normal"]))
    member_data = [["Nome", "Papel"]]
    for member in members:
        role = "Orientador" if member["can_record_minutes"] else "Avaliador"
        member_data.append([_p(member["name"], styles["SmallWrap"]), role])
    story.append(_table(member_data, [11 * cm, 6 * cm], header=True))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Resumo das notas</b>", styles["Normal"]))
    summary_data = [["Avaliador", "Média", "Notas lançadas"]]
    for row in summary:
        average = "" if row["average_grade"] is None else f"{float(row['average_grade']):.2f}"
        summary_data.append([_p(row["advisor_name"], styles["SmallWrap"]), average, str(row["grades_count"])])
    if len(summary_data) == 1:
        summary_data.append(["-", "Sem notas lançadas", "-"])
    story.append(_table(summary_data, [8 * cm, 4 * cm, 5 * cm], header=True))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Notas por critério</b>", styles["Normal"]))
    grades_by_key = {(row["advisor_id"], row["criterion_id"]): row for row in grades}
    evaluators = [member for member in members if member["can_grade"]]
    detail_data = [["Critério", "Avaliador", "Nota", "Observação"]]
    for criterion in criteria_rows:
        for evaluator in evaluators:
            grade_row = grades_by_key.get((evaluator["advisor_id"], criterion["id"]), {})
            grade = grade_row.get("grade")
            detail_data.append([
                _p(criterion["criterion"], styles["SmallWrap"]),
                _p(evaluator["name"], styles["SmallWrap"]),
                "" if grade is None else f"{float(grade):.2f}",
                _p(grade_row.get("observation") or "", styles["SmallWrap"]),
            ])
    story.append(_table(detail_data, [4.6 * cm, 4.4 * cm, 2 * cm, 6 * cm], header=True))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Composição da nota</b>", styles["Normal"]))
    average = final_grade.get("average_grade")
    is_plan_occupation = "plano" in str(board["stage"]).lower() and "ocupa" in str(board["stage"]).lower()
    if average is None:
        result_data = [["Componente", "Nota bruta", "Valor ponderado"], ["Média dos avaliadores x 0,7", "Sem notas lançadas", "-"]]
    elif is_plan_occupation:
        average_value = float(average)
        partial_1_value = float(board.get("plan_partial_1") or 0)
        partial_2_value = float(board.get("plan_partial_2") or 0)
        final_value = calculate_plan_occupation_grade(partial_1_value, partial_2_value, average_value)
        status = "Aprovado" if final_value is not None and final_value >= 7 else "Reprovado em banca"
        result_data = [
            ["Componente", "Nota bruta", "Valor ponderado"],
            ["Parcial 1 x 0,1", f"{partial_1_value:.2f}", f"{partial_1_value * 0.1:.2f}"],
            ["Parcial 2 x 0,2", f"{partial_2_value:.2f}", f"{partial_2_value * 0.2:.2f}"],
            ["Média dos avaliadores x 0,7", f"{average_value:.2f}", f"{average_value * 0.7:.2f}"],
            ["Nota final", "-", "-" if final_value is None else f"{final_value:.2f}"],
            ["Situação", status, "-"],
        ]
    else:
        average_value = float(average)
        status = "Aprovado" if average_value >= 7 else "Reprovado em banca"
        result_data = [
            ["Componente", "Peso", "Nota considerada"],
            ["Média da banca", "100%", f"{average_value:.2f}"],
            ["Nota final", "100%", f"{average_value:.2f}"],
            ["Situação", "-", status],
        ]
    story.append(_table(result_data, [7 * cm, 5 * cm, 5 * cm], header=True))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Ata da banca</b>", styles["Normal"]))
    minutes_text = minutes["minutes_text"] if minutes else "Ata ainda não registrada."
    story.append(_table([[Paragraph(minutes_text, styles["SmallWrap"])]], [17 * cm]))

    doc.build(story)
    return path


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="SmallWrap", fontSize=8, leading=10, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="HeadingClean", fontSize=14, leading=18, spaceAfter=8, alignment=1))
    return styles


def _institutional_logo(styles):
    if not LOGO_PATH.exists():
        return Paragraph("<b>Espaço para logo institucional</b>", styles["Small"])

    image = Image(str(LOGO_PATH))
    max_width = 3.6 * cm
    max_height = 1.8 * cm
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    image.hAlign = "CENTER"
    return image


def _table(data, col_widths, header: bool = False):
    table = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke if header else colors.white),
    ]
    if header:
        style.append(("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"))
    table.setStyle(TableStyle(style))
    return table


def _p(text: str, style):
    return Paragraph(text or "", style)


def latest_pdf_for_record(record_id: int) -> Path | None:
    rows = query("SELECT file_path FROM pdf_exports WHERE record_id = ? ORDER BY generated_at DESC LIMIT 1", (record_id,))
    if not rows:
        return None
    return Path(rows[0]["file_path"])
