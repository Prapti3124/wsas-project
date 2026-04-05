import subprocess
import os

try:
    cmd = ["git", "show", "73b64a7:frontend/index.html"]
    old_html = subprocess.check_output(cmd, text=True, encoding='utf-8')
    
    start_idx = old_html.find('<section id="otp-verify"')
    end_idx = old_html.find('</section>', start_idx) + len('</section>')
    otp_section = old_html[start_idx:end_idx]
    
    current_idx_path = "frontend/index.html"
    with open(current_idx_path, "r", encoding="utf-8") as f:
        current_html = f.read()
        
    insert_point = current_html.find('<!-- ── MAIN DASHBOARD (shown after login) ────────────────────────────────── -->')
    
    new_html = current_html[:insert_point] + "\n  <!-- ── OTP VERIFICATION ─────────────────────────────────────────────────── -->\n  " + otp_section + "\n\n  " + current_html[insert_point:]
    
    new_html = new_html.replace('id="registerError" class="alert alert-danger d-none mt-3"', 'id="registerError" class="alert alert-danger d-none mt-3" style="color: #842029 !important; font-weight: bold;"')
    
    with open(current_idx_path, "w", encoding="utf-8") as f:
        f.write(new_html)
        
    print("OTP section injected successfully!")
    
except Exception as e:
    print(f"Error: {e}")
