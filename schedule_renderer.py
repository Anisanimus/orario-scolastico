"""Modulo dedicato al rendering HTML delle tabelle orario (Classi, Docenti, Aule, Sostegno, DVA)."""
from typing import List, Optional, Any, Dict

def render_html_schedule_table(
    days_active: List[str],
    daily_hours: List[int],
    grid_matrix: List[List[Any]],
    view_type: str = "class",
    day_has_lessons: Optional[List[bool]] = None
) -> str:
    max_h = max(daily_hours) if daily_hours else 6
    num_days = len(days_active)
    day_col_width = f"{92 // num_days}%" if num_days > 0 else "18%"
    
    html = f"""
    <div style="width: 100%; overflow-x: auto; margin: 15px 0 25px 0; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); background: #ffffff;">
      <table style="width: 100%; border-collapse: collapse; table-layout: fixed; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 13px;">
        <thead>
          <tr style="background: #f8fafc; border-bottom: 2px solid #e2e8f0;">
            <th style="width: 70px; min-width: 65px; padding: 12px 6px; text-align: center; color: #475569; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; border-right: 1px solid #e2e8f0;">Ora</th>
    """
    for d_name in days_active:
        html += f"""
            <th style="width: {day_col_width}; min-width: 130px; padding: 12px 8px; text-align: center; color: #1e293b; font-size: 13px; font-weight: 700; border-right: 1px solid #e2e8f0;">{d_name}</th>
        """
    html += """
          </tr>
        </thead>
        <tbody>
    """
    for h in range(max_h):
        ora_label = f"{h+1}ª Ora"

        html += f"""
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 4px; text-align: center; font-weight: 700; color: #475569; background: #f8fafc; font-size: 11.5px; border-right: 1px solid #e2e8f0;">{ora_label}</td>
        """
        for d_idx, day_name in enumerate(days_active):
            if h >= daily_hours[d_idx]:
                html += """<td style="background: #f8fafc; border-right: 1px solid #f1f5f9;"></td>"""
                continue
                
            is_free_day = (day_has_lessons is not None and not day_has_lessons[d_idx])
            if is_free_day and view_type == "teacher":
                html += """
                <td style="padding: 6px; vertical-align: middle; text-align: center; background: #f0fdf4; border-right: 1px solid #e2e8f0;">
                  <div style="background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px 4px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;">🏖️ GIORNO LIBERO</div>
                </td>
                """
                continue

            slot = grid_matrix[d_idx][h] if (d_idx < len(grid_matrix) and h < len(grid_matrix[d_idx])) else None
            if slot is not None:
                accent_c = getattr(slot, "subject_color", "#3498db") or "#3498db"
                clean_c = slot.class_name.replace("ª", "").replace(" ", "") if slot.class_name else ""
                clean_s = slot.subject_name.split("(")[0].strip() if slot.subject_name else ""
                clean_r = slot.room_name.split("(")[0].strip().replace("ª", "").replace("  ", " ") if getattr(slot, "room_name", None) else ""
                
                room_badge = ""
                if clean_r:
                    room_badge = f"""<div style="margin-top: 4px; display: inline-block; background: #e0f2fe; color: #0369a1; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 600;">📍 {clean_r}</div>"""

                comp_badge = ""
                if getattr(slot, "is_compresenza", False) or getattr(slot, "compresenza_text", ""):
                    c_txt = getattr(slot, "compresenza_text", "") or "Compresenza"
                    comp_badge = f"""<div style="margin-top: 4px; display: inline-block; background: #fef3c7; color: #92400e; border: 1px solid #fde68a; border-radius: 4px; padding: 2px 6px; font-size: 10.5px; font-weight: 700;">👥 {c_txt}</div>"""

                if view_type == "support_teacher":
                    stud_txt = f"♿ {slot.student_name}" if getattr(slot, 'student_name', None) else (f"[{slot.activity_type.upper()}]" if getattr(slot, 'is_enhancement', False) else "Sostegno")
                    sub_cur = f"📖 {slot.curricular_subject_name}" if getattr(slot, 'curricular_subject_name', None) else ""
                    cur_t = f"👤 con {slot.curricular_teacher_name}" if getattr(slot, 'curricular_teacher_name', None) else ""
                    content = f"""
                    <div style="border: 1px solid #e2e8f0; border-left: 4px solid #8b5cf6; background: #ffffff; border-radius: 6px; padding: 6px 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                      <div style="font-weight: 700; color: #1e293b; font-size: 13px;">🏫 Classe {clean_c}</div>
                      <div style="color: #6b21a8; font-size: 11.5px; font-weight: 700; margin-top: 2px;">{stud_txt}</div>
                      <div style="color: #475569; font-size: 11px; margin-top: 2px;">{sub_cur} {cur_t}</div>
                      {room_badge}
                    </div>
                    """
                elif view_type == "class_with_support":
                    cur_sl = slot.get('curricular') if isinstance(slot, dict) else slot
                    sup_list = slot.get('support', []) if isinstance(slot, dict) else []
                    
                    c_s = getattr(cur_sl, 'subject_name', '').split('(')[0].strip() if cur_sl else ''
                    c_t = getattr(cur_sl, 'teacher_name', '') if cur_sl else ''
                    c_r = getattr(cur_sl, 'room_name', '').split('(')[0].strip().replace('ª', '').replace('  ', ' ') if getattr(cur_sl, 'room_name', None) else ''
                    r_bdg = f"""<div style="margin-top: 3px; display: inline-block; background: #e0f2fe; color: #0369a1; border-radius: 4px; padding: 1px 5px; font-size: 10px; font-weight: 600;">📍 {c_r}</div>""" if c_r else ''
                    
                    sup_badges = ''
                    for s_item in sup_list:
                        st_name = getattr(s_item, 'teacher_name', '')
                        st_stud = getattr(s_item, 'student_name', '')
                        stud_info = f" ({st_stud})" if st_stud else ""
                        sup_badges += f"""<div style="margin-top: 3px; display: inline-block; background: #f3e8ff; color: #6b21a8; border: 1px solid #d8b4fe; border-radius: 4px; padding: 2px 6px; font-size: 10.5px; font-weight: 700;">♿ {st_name}{stud_info}</div>"""
                        
                    content = f"""
                    <div style="border: 1px solid #e2e8f0; border-left: 4px solid {accent_c}; background: #ffffff; border-radius: 6px; padding: 6px 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                      <div style="font-weight: 700; color: #1e293b; font-size: 13px;">📖 {c_s}</div>
                      <div style="color: #475569; font-size: 12px; margin-top: 2px; font-weight: 500;">👤 {c_t}</div>
                      {r_bdg}
                      {comp_badge}
                      {sup_badges}
                    </div>
                    """
                elif view_type == "dva_student":
                    cur_sub = getattr(slot, "curricular_subject_name", "") if slot else ""
                    cur_t = getattr(slot, "curricular_teacher_name", "") if slot else ""
                    t_name = getattr(slot, "teacher_name", "") if slot else ""
                    content = f"""
                    <div style="border: 1px solid #e2e8f0; border-left: 4px solid #10b981; background: #ffffff; border-radius: 6px; padding: 6px 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                      <div style="font-weight: 700; color: #065f46; font-size: 12.5px;">🟢 {t_name}</div>
                      <div style="color: #475569; font-size: 11px; margin-top: 2px;">📖 {cur_sub} (con {cur_t})</div>
                      {room_badge}
                    </div>
                    """
                elif view_type == "teacher":
                    content = f"""
                    <div style="border: 1px solid #e2e8f0; border-left: 4px solid {accent_c}; background: #ffffff; border-radius: 6px; padding: 6px 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                      <div style="font-weight: 700; color: #1e293b; font-size: 13px;">🏫 Classe {clean_c}</div>
                      <div style="color: #475569; font-size: 12px; margin-top: 2px; font-weight: 500;">📖 {clean_s}</div>
                      {room_badge}
                      {comp_badge}
                    </div>
                    """
                elif view_type == "class":
                    content = f"""
                    <div style="border: 1px solid #e2e8f0; border-left: 4px solid {accent_c}; background: #ffffff; border-radius: 6px; padding: 6px 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                      <div style="font-weight: 700; color: #1e293b; font-size: 13px;">📖 {clean_s}</div>
                      <div style="color: #475569; font-size: 12px; margin-top: 2px; font-weight: 500;">👤 {slot.teacher_name}</div>
                      {room_badge}
                      {comp_badge}
                    </div>
                    """
                else: # room
                    content = f"""
                    <div style="border: 1px solid #e2e8f0; border-left: 4px solid {accent_c}; background: #ffffff; border-radius: 6px; padding: 6px 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                      <div style="font-weight: 700; color: #1e293b; font-size: 13px;">🏫 Classe {clean_c}</div>
                      <div style="color: #475569; font-size: 12px; margin-top: 2px; font-weight: 500;">📖 {clean_s}</div>
                      <div style="color: #64748b; font-size: 11px; margin-top: 2px;">👤 {slot.teacher_name}</div>
                      {comp_badge}
                    </div>
                    """
                html += f"""<td style="padding: 5px; vertical-align: top; border-right: 1px solid #f1f5f9;">{content}</td>"""
            else:
                if view_type in ("teacher", "support_teacher"):
                    day_lessons = [grid_matrix[d_idx][hh] is not None for hh in range(daily_hours[d_idx])]
                    first_l = next((idx for idx, val in enumerate(day_lessons) if val), None)
                    last_l = next((idx for idx in reversed(range(len(day_lessons))) if day_lessons[idx]), None)
                    
                    if first_l is not None and last_l is not None and first_l < h < last_l:
                        empty_content = """<div style="background: #fef3c7; color: #b45309; border: 1px solid #fde68a; border-radius: 6px; padding: 8px 4px; text-align: center; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;">☕ ORA BUCA</div>"""
                    else:
                        empty_content = """<div style="text-align: center; color: #cbd5e1; font-weight: bold; padding: 8px 0;">-</div>"""
                elif view_type == "room":
                    empty_content = """<div style="background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; border-radius: 6px; padding: 6px 4px; text-align: center; font-size: 11px; font-weight: 600;">🟢 Libera</div>"""
                else:
                    empty_content = """<div style="text-align: center; color: #cbd5e1; font-weight: bold; padding: 8px 0;">-</div>"""
                    
                html += f"""<td style="padding: 5px; vertical-align: middle; border-right: 1px solid #f1f5f9;">{empty_content}</td>"""
                
        html += """</tr>"""
        
    html += """
        </tbody>
      </table>
    </div>
    """
    return html

