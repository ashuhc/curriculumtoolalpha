from PIL import Image, ImageDraw, ImageFont

def draw_curriculum_diagram(output_filename="curriculum_flowchart.png"):
    # Canvas Dimensions
    width, height = 1200, 1000
    img = Image.new("RGB", (width, height), color="#F8FAFC")
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        title_font = ImageFont.truetype("arial.ttf", 20)
        bold_font = ImageFont.truetype("arialbd.ttf", 14)
        regular_font = ImageFont.truetype("arial.ttf", 12)
    except OSError:
        # Fallback for systems without Arial
        title_font = ImageFont.load_default()
        bold_font = ImageFont.load_default()
        regular_font = ImageFont.load_default()

    # Helper function to draw rounded boxes with text
    def draw_box(x, y, w, h, title, items, bg_color, border_color, title_color):
        # Background box
        draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=bg_color, outline=border_color, width=2)
        # Title
        draw.text((x + 12, y + 10), title, fill=title_color, font=bold_font)
        # Bullet items
        curr_y = y + 30
        for item in items:
            draw.text((x + 12, curr_y), f"• {item}", fill="#334155", font=regular_font)
            curr_y += 18

    # Helper function to draw directed arrows
    def draw_arrow(start, end, color="#64748B"):
        x1, y1 = start
        x2, y2 = end
        draw.line([x1, y1, x2, y2], fill=color, width=2)
        # Arrowhead
        if y1 < y2:  # Downward
            draw.polygon([(x2 - 5, y2 - 6), (x2 + 5, y2 - 6), (x2, y2)], fill=color)
        elif x1 < x2:  # Rightward
            draw.polygon([(x2 - 6, y2 - 5), (x2 - 6, y2 + 5), (x2, y2)], fill=color)

    # -------------------------------------------------------------------------
    # 1. INPUTS SECTION (Top)
    # -------------------------------------------------------------------------
    draw.text((40, 20), "1. INPUTS (Starting Point)", fill="#0288D1", font=title_font)
    
    inputs = [
        ("Course Catalog Data", ["1000/3000/4000 Levels", "Core / Elective / Capstone", "Prerequisite Rules"]),
        ("Past Enrollment Data", ["Historical Class Sizes", "Course Demand Estimates"]),
        ("Teacher Preferences", ["Google Form Responses", "Desired Courses & Times", "Teaching History"]),
        ("Faculty Roster & Types", ["Tenured (3 courses/yr)", "Full-Time/Temp (6/yr)", "Adjuncts (1-2/yr)"]),
        ("Section Constraints", ["Remote Cap: 25", "Small Class: 40-45", "Large Class: ~200"])
    ]

    in_x_start = 40
    in_w = 210
    in_gap = 20
    in_y = 55
    in_h = 95

    for i, (title, items) in enumerate(inputs):
        x = in_x_start + i * (in_w + in_gap)
        draw_box(x, in_y, in_w, in_h, title, items, "#E1F5FE", "#0288D1", "#01579B")
        # Draw arrow pointing down to processing
        draw_arrow((x + in_w // 2, in_y + in_h), (x + in_w // 2, in_y + in_h + 40))

    # -------------------------------------------------------------------------
    # 2. PROCESSING ENGINE SECTION (Middle)
    # -------------------------------------------------------------------------
    draw.text((40, 210), "2. PROCESSING ENGINE", fill="#E65100", font=title_font)

    processes = [
        ("A. Ingest & Validate Data", ["Exclude Graduate Courses (5000+)", "Validate Catalog & Prerequisites"]),
        ("B. Demand & Capacity Planning", ["Estimate Required Sections", "Apply Capacity Caps & Sizes"]),
        ("C. Instructor & Workload Match", ["Prioritize Mandatory Core Courses", "Match Preferences & Targets"]),
        ("D. Schedule & Slot Optimization", ["Assign Time Slots", "Diversify & Prevent Overlaps"]),
        ("E. Conflict Detection & Flagging", ["Flag Unstaffed Core Courses", "Identify Workload Mismatches"])
    ]

    p_x = 40
    p_w = 1130
    p_y_start = 245
    p_h = 75
    p_gap = 35

    for i, (title, items) in enumerate(processes):
        y = p_y_start + i * (p_h + p_gap)
        draw_box(p_x, y, p_w, p_h, title, items, "#FFF3E0", "#F57C00", "#E65100")
        if i < len(processes) - 1:
            draw_arrow((p_x + p_w // 2, y + p_h), (p_x + p_w // 2, y + p_h + p_gap))

    # -------------------------------------------------------------------------
    # 3. OUTPUTS & OUT OF SCOPE (Bottom)
    # -------------------------------------------------------------------------
    last_p_bottom = p_y_start + 4 * (p_h + p_gap) + p_h
    out_y_start = last_p_bottom + 60

    # Arrows to outputs
    draw_arrow((p_x + 280, last_p_bottom), (p_x + 280, out_y_start - 5))
    draw_arrow((p_x + 850, last_p_bottom), (p_x + 850, out_y_start - 5))

    # Outputs
    draw.text((40, out_y_start - 35), "3. OUTPUTS (Ending Point)", fill="#1B5E20", font=title_font)
    
    draw_box(40, out_y_start, 540, 110, "Master Undergraduate Curriculum", 
             ["Offered Course List", "Section Counts & Capacities", "Assigned Time Slots", "Assigned Instructors"], 
             "#E8F5E9", "#388E3C", "#1B5E20")

    draw_box(630, out_y_start, 540, 110, "Unresolved Conflicts Report", 
             ["Core Courses Lacking Instructors", "Workload Over/Under Allocations", "Schedule Overlaps"], 
             "#E8F5E9", "#388E3C", "#1B5E20")

    # Save to PNG image file
    img.save(output_filename)
    print(f"Image successfully generated: {output_filename}")

if __name__ == "__main__":
    draw_curriculum_diagram()