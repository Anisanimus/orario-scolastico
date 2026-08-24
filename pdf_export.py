# PDF export module
import io
from typing import List, Optional, Any
from models import TimetableProblem
from solver import TimetableResult

def generate_pdf_from_html(html_content: str) -> bytes:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_content, wait_until='networkidle')
        pdf_bytes = page.pdf(
            format='A4',
            landscape=True,
            print_background=True,
            margin={'top': '10mm', 'bottom': '10mm', 'left': '12mm', 'right': '12mm'}
        )
        browser.close()
        return pdf_bytes

def _build_html_document(title: str, pages_html: List[str]) -> str:
    css_styles = '''
    <style>
      @page { size: A4 landscape; margin: 10mm 12mm; }
      * { box-sizing: border-box; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
      body { font-family: -Apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; margin: 0; padding: 0; background: #ffffff; color: #1e293b; }
      .sheet-page { page-break-after: always; width: 100%; min-height: 180mm; display: flex; flex-direction: column; justify-content: flex-start; padding: 4px 0 10px 0; }
      .sheet-page:last-child { page-break-after: avoid; }
      .header-bar { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0284c7; padding-bottom: 8px; margin-bottom: 12px; }
      .header-title { font-size: 18px; font-weight: 700; color: #0f172a; }
      .header-subtitle { font-size: 12px; color: #64748b; font-weight: 500; }
      table.schedule-grid { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 11.5px; }
      table.schedule-grid th { background: #f8fafc; border: 1px solid #cbd5e1; padding: 8px 4px; text-align: center; font-weight: 700; color: #1e293b; }
      table.schedule-grid td { border: 1px solid #cbd5e1; padding: 4px; vertical-align: top; height: 65px; }
      .cell-content { height: 100%; background: #ffffff; border-radius: 5px; padding: 4px 6px; display: flex; flex-direction: column; justify-content: space-between; }
      .badge-room { display: inline-block; background: #e0f2fe; color: #0369a1; border-radius: 4px; padding: 1px 5px; font-size: 9.5px; font-weight: 600; margin-top: 3px; }
      .badge-comp { display: inline-block; background: #fef3c7; color: #92400e; border: 1px solid #fde68a; border-radius: 4px; padding: 1px 5px; font-size: 9px; font-weight: 700; margin-top: 3px; }
      .free-day-box { height: 100%; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #15803d; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; }
      .gap-box { height: 100%; background: #fef3c7; border: 1px solid #fde68a; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #b45309; font-weight: 700; font-size: 10px; }
      .free-slot { height: 100%; display: flex; align-items: center; justify-content: center; color: #cbd5e1; font-weight: bold; }
    </style>
    '''
    pages_combined = '\n'.join(pages_html)
    return f'<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8"><title>{title}</title>{css_styles}</head><body>{pages_combined}</body></html>'

def _render_single_sheet_grid(title_main: str, subtitle_info: str, school_name: str, days_active: List[str], daily_hours: List[int], grid_matrix: List[str], view_type: str = 'class', day_has_lessons: Optional[List[bool]] = None) -> str:
    max_h = max(daily_hours) if daily_hours else 6
    num_days = len(days_active)
    day_col_width = f"{90 // num_days}%" if num_days > 0 else "18%"
    rows_html = ''
    for h in range(max_h):
        cells_html = f'<td style="width: 55px; text-align: center; font-weight: 700; background: #f8fafc; color: #475569; vertical-align: middle;">{h+1}a Ora</td>'
        for d_idx, day_name in enumerate(days_active):
            if h >= daily_hours[d_idx]:
                cells_html += '<td style="background: #f8fafc;"></td>'
                continue
            if_free = (day_has_lessons is not None and not day_has_lessons[d_idx])
            if if_free and view_type == 'teacher':
                cells_html += '<td><div class="free-day-box">GIORNO LIBERO</div></td>'
                continue
            slot = grid_matrix[d_idx][h] if (d_idx < len(grid_matrix) and h < len(grid_matrix[d_idx])) else None
            if slot is not None:
                accent_c = getattr(slot, 'subject_color', '#0284c7') or '#0284c7'
                clean_c = getattr(slot, 'class_name', '').replace('ª', '').replace(' ', '') if getattr(slot, 'class_name', None) else ''
                clean_s = getattr(slot, 'subject_name', '').split('(')[0].strip() if getattr(slot, 'subject_name', None) else ''
                clean_r = getattr(slot, 'room_name', '').split('(')[0].strip().replace('ª', '').replace('  ', ' ') if getattr(slot, 'room_name', None) else ''
                room_badge = f'<div class="badge-room">{clean_r}</div>' if clean_r else ''
                comp_badge = ''
                if getattr(slot, 'is_compresenza', False) or getattr(slot, 'compresenza_text', ''):
                    ct = getattr(slot, 'compresenza_text', '') or 'Compresenza'
                    comp_badge = f'<div class="badge-comp">{ct}</div>'
                
                if view_type == 'support_teacher':
                    stud_txt = f"♿ {slot.student_name}" if getattr(slot, 'student_name', None) else (f"[{slot.activity_type.upper()}]" if getattr(slot, 'is_enhancement', False) else "Sostegno")
                    sub_cur = f"📖 {slot.curricular_subject_name}" if getattr(slot, 'curricular_subject_name', None) else ""
                    cur_t = f"👤 con {slot.curricular_teacher_name}" if getattr(slot, 'curricular_teacher_name', None) else ""
                    card_body = f'<div class="cell-content" style="border-left: 4px solid #8b5cf6;"><div><div style="font-weight: 700; color: #0f172a; font-size: 12px;">Classe {clean_c}</div><div style="color: #6b21a8; font-size: 10.5px; font-weight: 700; margin-top: 1px;">{stud_txt}</div><div style="color: #475569; font-size: 10px; margin-top: 2px;">{sub_cur} {cur_t}</div></div><div>{room_badge}</div></div>'
                elif view_type == 'class_with_support':
                    cur_sl = slot.get('curricular') if isinstance(slot, dict) else slot
                    sup_list = slot.get('support', []) if isinstance(slot, dict) else []
                    
                    c_s = getattr(cur_sl, 'subject_name', '').split('(')[0].strip() if cur_sl else ''
                    c_t = getattr(cur_sl, 'teacher_name', '') if cur_sl else ''
                    c_r = getattr(cur_sl, 'room_name', '').split('(')[0].strip() if getattr(cur_sl, 'room_name', None) else ''
                    r_bdg = f'<div class="badge-room">{c_r}</div>' if c_r else ''
                    
                    sup_badges = ''
                    for s_item in sup_list:
                        st_name = getattr(s_item, 'teacher_name', '')
                        st_stud = getattr(s_item, 'student_name', '')
                        stud_info = f" ({st_stud})" if st_stud else ""
                        sup_badges += f'<div style="background: #f3e8ff; color: #6b21a8; border: 1px solid #d8b4fe; border-radius: 4px; padding: 1px 4px; font-size: 8.5px; font-weight: 700; margin-top: 2px;">♿ {st_name}{stud_info}</div>'
                        
                    card_body = f'<div class="cell-content" style="border-left: 4px solid {accent_c};"><div><div style="font-weight: 700; color: #0f172a; font-size: 11.5px;">{c_s}</div><div style="color: #475569; font-size: 10.5px; margin-top: 1px; font-weight: 500;">{c_t}</div></div><div>{r_bdg}{sup_badges}</div></div>'
                elif view_type == 'teacher':
                    card_body = f'<div class="cell-content" style="border-left: 4px solid {accent_c};"><div><div style="font-weight: 700; color: #0f172a; font-size: 12px;">Classe {clean_c}</div><div style="color: #475569; font-size: 11px; margin-top: 1px; font-weight: 500;">{clean_s}</div></div><div>{room_badge}{comp_badge}</div></div>'
                elif view_type == 'class':
                    card_body = f'<div class="cell-content" style="border-left: 4px solid {accent_c};"><div><div style="font-weight: 700; color: #0f172a; font-size: 12px;">{clean_s}</div><div style="color: #475569; font-size: 11px; margin-top: 1px; font-weight: 500;">{slot.teacher_name}</div></div><div>{room_badge}{comp_badge}</div></div>'
                else:
                    card_body = f'<div class="cell-content" style="border-left: 4px solid {accent_c};"><div><div style="font-weight: 700; color: #0f172a; font-size: 12px;">Classe {clean_c}</div><div style="color: #475569; font-size: 11px; margin-top: 1px; font-weight: 500;">{clean_s}</div><div style="color: #64748b; font-size: 10px;">{slot.teacher_name}</div></div><div>{comp_badge}</div></div>'
                cells_html += f'<td>{card_body}</td>'
            else:
                if view_type in ('teacher', 'support_teacher'):
                    day_lessons = [grid_matrix[d_idx][hh] is not None for hh in range(daily_hours[d_idx])]
                    first_l = next((idx for idx, val in enumerate(day_lessons) if val), None)
                    last_l = next((idx for idx in reversed(range(len(day_lessons))) if day_lessons[idx]), None)
                    if first_l is not None and last_l is not None and first_l < h < last_l:
                        empty_body = '<div class="gap-box">ORA BUCA</div>'
                    else:
                        empty_body = '<div class="free-slot">-</div>'
                elif view_type == 'room':
                    empty_body = '<div class="free-slot" style="color: #16a34a; font-size: 10px;">Libera</div>'
                else:
                    empty_body = '<div class="free-slot">-</div>'
                cells_html += f'<td>{empty_body}</td>'
        rows_html += f'<tr>{cells_html}</tr>'

    header_cols = '<th style="width: 55px;">Ora</th>'
    for d_name in days_active:
        header_cols += f'<th style="width: {day_col_width};">{d_name.upper()}</th>'
    return f' <div class="sheet-page"><div class="header-bar"><div><div class="header-title">{title_main}</div><div class="header-subtitle">{subtitle_info}</div></div><div style="text-align: right;"><div style="font-size: 13px; font-weight: 700; color: #0284c7;">{school_name.upper()}</div><div style="font-size: 11px; color: #64748b;">Orario Scolastico Ufficiale</div></div></div><table class="schedule-grid"><thead><tr>{header_cols}</tr></thead><tbody>{rows_html}</tbody></table></div>'

def generate_classes_pdf(problem: TimetableProblem, result: TimetableResult) -> bytes:
    days_active = problem.config.active_days
    daily_hours = problem.config.daily_hours[:problem.config.num_days]
    school_name = problem.config.school_name
    pages = []
    for c_id, c_obj in problem.classes.items():
        if c_id in result.grid_by_class:
            grid = result.grid_by_class[c_id]
            clean_c = c_obj.name.replace('ª', '').replace(' ', '')
            title = f'Orario Settimanale - Classe {clean_c}'
            sub = 'Modello DADA - Aule Disciplinari' if problem.config.is_dada else 'Anno Scolastico 2026/2027'
            pages.append(_render_single_sheet_grid(title, sub, school_name, days_active, daily_hours, grid, view_type='class'))
    full_html = _build_html_document(f'Orario Classi - {school_name}', pages)
    return generate_pdf_from_html(full_html)

def generate_teachers_pdf(problem: TimetableProblem, result: TimetableResult) -> bytes:
    days_active = problem.config.active_days
    daily_hours = problem.config.daily_hours[:problem.config.num_days]
    school_name = problem.config.school_name
    num_days = problem.config.num_days
    pages = []
    for t_id, t_obj in problem.teachers.items():
        is_sostegno = (
            "sostegno" in t_obj.name.lower() or 
            "sostegno" in getattr(t_obj, "cdc", "").lower() or 
            "admm" in getattr(t_obj, "cdc", "").lower()
        )
        if is_sostegno:
            continue
            
        t_assignments = [a for a in problem.assignments if a.teacher_id == t_id]
        if not t_assignments or sum(a.hours_per_week for a in t_assignments) == 0:
            continue

        if t_id in result.grid_by_teacher:
            grid = result.grid_by_teacher[t_id]
            has_curricular_lessons = any(grid[d][h] is not None for d in range(num_days) for h in range(daily_hours[d]))
            if not has_curricular_lessons:
                continue
                
            day_has_lessons = [False] * num_days
            for d_idx in range(num_days):
                for h in range(daily_hours[d_idx]):
                    if grid[d_idx][h] is not None:
                        day_has_lessons[d_idx] = True
                        break
            title = f'Orario Settimanale - {t_obj.name}'
            free_info = f'Giorno Libero: {t_obj.free_day_1}' if t_obj.free_day_1 else 'Tempo Pieno'
            sub = f"{getattr(t_obj, 'cdc', 'Docente') or 'Docente'} | {free_info}"
            pages.append(_render_single_sheet_grid(title, sub, school_name, days_active, daily_hours, grid, view_type='teacher', day_has_lessons=day_has_lessons))
    full_html = _build_html_document(f'Orario Docenti - {school_name}', pages)
    return generate_pdf_from_html(full_html)

def generate_support_teachers_pdf(problem: TimetableProblem, curricular_result: Optional[Any], support_result: Optional[Any]) -> bytes:
    """Genera il PDF per i docenti di sostegno e potenziamento con layout grafico completo."""
    if not support_result:
        return b''
    days_active = problem.config.active_days
    daily_hours = problem.config.daily_hours[:problem.config.num_days]
    school_name = problem.config.school_name
    num_days = problem.config.num_days
    pages = []
    
    for t_id, t_obj in problem.teachers.items():
        if t_id not in support_result.grid_by_support_teacher:
            continue
            
        grid_raw = support_result.grid_by_support_teacher[t_id]
        has_active_hours = any(grid_raw[d][h] for d in range(num_days) for h in range(daily_hours[d]))
        if not has_active_hours:
            continue
            
        # Costruisci griglia con singolo slot
        grid = []
        for d in range(num_days):
            day_row = []
            for h in range(daily_hours[d]):
                slots = grid_raw[d][h]
                day_row.append(slots[0] if slots else None)
            grid.append(day_row)
            
        day_has_lessons = [False] * num_days
        for d_idx in range(num_days):
            for h in range(daily_hours[d_idx]):
                if grid[d_idx][h] is not None:
                    day_has_lessons[d_idx] = True
                    break
                    
        title = f'Orario Settimanale Sostegno - {t_obj.name}'
        tot_h = sum(sa.hours_per_week for sa in problem.support_assignments if sa.teacher_id == t_id)
        sub = f"Docente di Sostegno & Inclusione | Cattedra {tot_h}h"
        pages.append(_render_single_sheet_grid(title, sub, school_name, days_active, daily_hours, grid, view_type='support_teacher', day_has_lessons=day_has_lessons))
        
    full_html = _build_html_document(f'Orario Docenti Sostegno - {school_name}', pages)
    return generate_pdf_from_html(full_html)

def generate_classes_with_support_pdf(problem: TimetableProblem, curricular_result: Optional[Any], support_result: Optional[Any]) -> bytes:
    """Genera il PDF per le classi con l'orario curricolare integrato con i docenti di sostegno."""
    if not curricular_result:
        return b''
    days_active = problem.config.active_days
    daily_hours = problem.config.daily_hours[:problem.config.num_days]
    school_name = problem.config.school_name
    num_days = problem.config.num_days
    pages = []
    
    for c_id, c_obj in problem.classes.items():
        if c_id not in curricular_result.grid_by_class:
            continue
            
        c_cur_grid = curricular_result.grid_by_class[c_id]
        c_sup_grid = support_result.grid_by_class_support.get(c_id, []) if support_result else []
        
        grid = []
        for d in range(num_days):
            day_row = []
            for h in range(daily_hours[d]):
                cur_slot = c_cur_grid[d][h] if d < len(c_cur_grid) and h < len(c_cur_grid[d]) else None
                sup_slots = c_sup_grid[d][h] if d < len(c_sup_grid) and h < len(c_sup_grid[d]) else []
                
                if cur_slot is not None or sup_slots:
                    combined = {
                        'curricular': cur_slot,
                        'support': sup_slots,
                        'subject_color': getattr(cur_slot, 'subject_color', '#0284c7') if cur_slot else '#8b5cf6'
                    }
                    day_row.append(combined)
                else:
                    day_row.append(None)
            grid.append(day_row)
            
        clean_c = c_obj.name.replace('ª', '').replace(' ', '')
        title = f'Orario Integrato & Inclusione - Classe {clean_c}'
        sub = 'Orario Curricolare Ufficiale con Docenti di Sostegno e Compresenze'
        pages.append(_render_single_sheet_grid(title, sub, school_name, days_active, daily_hours, grid, view_type='class_with_support'))
        
    full_html = _build_html_document(f'Orario Classi Integrato Sostegno - {school_name}', pages)
    return generate_pdf_from_html(full_html)

def generate_rooms_pdf(problem: TimetableProblem, result: TimetableResult) -> bytes:
    if not problem.rooms:
        return b''
    days_active = problem.config.active_days
    daily_hours: List[int] = problem.config.daily_hours[:problem.config.num_days]
    school_name = problem.config.school_name
    pages = []
    for r_id, r_obj in problem.rooms.items():
        if r_id in result.grid_by_room:
            grid = result.grid_by_room[r_id]
            title = f'OccupazioneSpazio - {r_obj.name}'
            subj_names = [problem.subjects[s].name for s in r_obj.subject_ids if s in problem.subjects]
            sub = f'Discipline: {", ".join(subj_names) if subj_names else "Generale"} | Capienza: {r_obj.capacity} classi'
            pages.append(_render_single_sheet_grid(title, sub, school_name, days_active, daily_hours, grid, view_type="room"))
    full_html = _build_html_document(f'Orario Aule - {school_name}', pages)
    return generate_pdf_from_html(full_html)
