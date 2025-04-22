import json
import yaml
import markdown
import base64
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from datetime import datetime
from weasyprint import HTML
from pygments.formatters import HtmlFormatter
from jinja2 import Template
from pathlib import Path
import os
import io
from PIL import Image
import re
import sys
from functools import partial

# Keys to skip from rendering in the meta section (handled specially or elsewhere)
EXCLUDED_KEYS = {"title", "tlp", "tags"}
# My preferred order for yaml
FIELD_ORDER = ["title", "date", "analyst", "file", "tlp", "tags", "aliases", "family", "campaign", "source", "confidence","verdict"]

class ReportGenerator:
    def __init__(self, root):
        self.root = root
        self.body_text = None
        self.recent_files = []
        
        # Load configuration
        try:
            self.settings = self._load_settings()
            self.template = self._load_template()
        except Exception as e:
            messagebox.showerror("Initialization Error", f"Failed to initialize: {e}")
            self.settings = {"font": "Arial, sans-serif", "margin": "1.5cm", "style": "default"}
            self.template = Template("<html><body>Error loading template.</body></html>")
        
        # Initialize UI
        self._init_ui()
    
    def _load_settings(self):
        """Load settings from JSON file."""
        script_dir = Path(__file__).parent.resolve()
        settings_path = script_dir / "settings.json"
        
        if not settings_path.exists():
            # Create default settings if not exist
            default_settings = {
                "font": "Arial, sans-serif",
                "margin": "1.5cm",
                "style": "default",
                "logo_path": "",
                "recent_files": []
            }
            settings_path.write_text(json.dumps(default_settings, indent=2), encoding="utf-8")
            return default_settings
            
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            self.recent_files = settings.get("recent_files", [])
            return settings
        except Exception as e:
            raise ValueError(f"Failed to load settings: {e}")
    
    def _save_settings(self):
        """Save current settings to JSON file."""
        script_dir = Path(__file__).parent.resolve()
        settings_path = script_dir / "settings.json"
        
        # Update recent files in settings
        self.settings["recent_files"] = self.recent_files[:10]  # Keep only the 10 most recent
        
        try:
            settings_path.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception as e:
            messagebox.showwarning("Settings Warning", f"Failed to save settings: {e}")
    
    def _load_template(self):
        """Load Jinja2 template from file."""
        script_dir = Path(__file__).parent.resolve()
        template_path = script_dir / "template.html"
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")
            
        try:
            return Template(template_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"Failed to load template: {e}")
    
    def _init_ui(self):
        """Initialize the Tkinter UI."""
        self.root.title("MD Report Generator v1")
        
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_document)
        file_menu.add_command(label="Open...", command=self.load_markdown_from_file)
        
        # Recent files submenu
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Open Recent", menu=self.recent_menu)
        self._update_recent_menu()
        
        file_menu.add_separator()
        file_menu.add_command(label="Save...", command=self.save_markdown)
        file_menu.add_separator()
        file_menu.add_command(label="Settings...", command=self.show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        
        # Export menu
        export_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Export", menu=export_menu)
        export_menu.add_command(label="Preview HTML", command=self.preview_html)
        export_menu.add_command(label="Generate PDF", command=self.generate_report)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
        # Main content
        main_frame = tk.Frame(self.root, padx=10, pady=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(main_frame, text="Markdown Content with YAML Frontmatter:").pack(anchor="w", pady=(5, 0))
        
        # Text area with scrollbars
        self.body_text = scrolledtext.ScrolledText(main_frame, height=30, width=100, wrap=tk.WORD)
        self.body_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Button frame
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(button_frame, text="Load .md File", command=self.load_markdown_from_file).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Save .md File", command=self.save_markdown).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Preview HTML", command=self.preview_html).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Generate Report", command=self.generate_report).pack(side=tk.RIGHT, padx=5)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def _update_recent_menu(self):
        """Update the recent files menu."""
        # Clear current menu items
        self.recent_menu.delete(0, tk.END)
        
        if not self.recent_files:
            self.recent_menu.add_command(label="(No recent files)", state=tk.DISABLED)
            return
            
        # Add recent files to menu
        for path in self.recent_files:
            if Path(path).exists():
                # Use partial to create a function with the path as a parameter
                self.recent_menu.add_command(
                    label=Path(path).name,
                    command=partial(self.open_recent_file, path)
                )
    
    def open_recent_file(self, path):
        """Open a file from the recent files list."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.body_text.delete("1.0", tk.END)
                self.body_text.insert(tk.END, f.read())
            
            # Move this file to the top of the recent list
            if path in self.recent_files:
                self.recent_files.remove(path)
            self.recent_files.insert(0, path)
            self._update_recent_menu()
            self._save_settings()
            
            self.status_var.set(f"Loaded: {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n{e}")
    
    def add_to_recent_files(self, path):
        """Add a file to the recent files list."""
        path_str = str(path)
        if path_str in self.recent_files:
            self.recent_files.remove(path_str)
        self.recent_files.insert(0, path_str)
        self._update_recent_menu()
        self._save_settings()
    
    def new_document(self):
        """Clear the text area for a new document."""
        if self.body_text.get("1.0", tk.END).strip():
            if not messagebox.askyesno("New Document", "Clear current content?"):
                return
                
        self.body_text.delete("1.0", tk.END)
        # Insert template frontmatter
        template_fm = """---
title: "Malware Analysis Report"
date: "%s"
author: "Analyst"
verdict: "Unknown"
tags: []
tlp: "AMBER"
---

# Executive Summary

# Technical Analysis

# Indicators of Compromise

# Recommendations

""" % datetime.now().strftime("%Y-%m-%d")
        self.body_text.insert("1.0", template_fm)
        self.status_var.set("New document created")
    
    def load_markdown_from_file(self):
        """Load markdown file into the GUI text box."""
        path = filedialog.askopenfilename(filetypes=[("Markdown files", "*.md")])
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.body_text.delete("1.0", tk.END)
                    self.body_text.insert(tk.END, f.read())
                
                # Add to recent files
                self.add_to_recent_files(path)
                self.status_var.set(f"Loaded: {path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file:\n{e}")
    
    def save_markdown(self):
        """Save current content to a markdown file."""
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown files", "*.md")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.body_text.get("1.0", tk.END))
                
                # Add to recent files
                self.add_to_recent_files(path)
                self.status_var.set(f"Saved: {path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file:\n{e}")
    
    def parse_frontmatter(self, md_text):
        """Extract YAML frontmatter and markdown content body."""
        lines = md_text.strip().splitlines()
        if lines and lines[0] == "---":
            try:
                end_index = lines[1:].index("---") + 1
                frontmatter = yaml.safe_load("\n".join(lines[1:end_index])) or {}
                body = "\n".join(lines[end_index+1:])
                return frontmatter, body
            except ValueError:
                # No closing frontmatter delimiter
                messagebox.showwarning("Warning", "YAML frontmatter is missing closing '---' delimiter. Treating entire content as markdown.")
                return {}, md_text
            except Exception as e:
                raise ValueError(f"Invalid YAML frontmatter: {e}")
        return {}, md_text
    
    def encode_image_base64(self, image_path):
        """Convert an image file to a base64 data URI for inline use."""
        try:
            script_dir = Path(__file__).parent.resolve()
            resolved_path = Path(image_path).resolve()
            
            # Simple path traversal protection
            if not (script_dir in resolved_path.parents or script_dir == resolved_path.parent):
                # If path is not relative to script directory, check if it's an absolute path
                if not resolved_path.exists():
                    raise FileNotFoundError(f"Image not found: {image_path}")
            
            # Try to optimize the image if it's large
            try:
                with Image.open(resolved_path) as img:
                    # If image is larger than 1MB, compress it
                    if resolved_path.stat().st_size > 1_000_000:
                        output = io.BytesIO()
                        
                        # Preserve transparent backgrounds in PNG
                        if img.format == 'PNG' and img.mode == 'RGBA':
                            img.save(output, format='PNG', optimize=True)
                        else:
                            # For JPG and other formats
                            img.save(output, format=img.format, optimize=True, quality=85)
                        
                        encoded = base64.b64encode(output.getvalue()).decode("utf-8")
                    else:
                        with open(resolved_path, "rb") as f:
                            encoded = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                # Fallback to direct file reading if PIL processing fails
                with open(resolved_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
            
            # Get the file extension and determine MIME type
            ext = resolved_path.suffix.lower().lstrip(".")
            mime_types = {
                "jpg": "jpeg", "jpeg": "jpeg", "png": "png", 
                "gif": "gif", "svg": "svg+xml", "webp": "webp"
            }
            mime = mime_types.get(ext, ext)
            
            return f"data:image/{mime};base64,{encoded}"
        except Exception as e:
            self.status_var.set(f"Warning: Failed to process image {image_path}")
            return ""
    
    def process_inline_images(self, md_content, base_dir=None):
        """Process all image references in markdown to embed them as base64."""
        if not base_dir:
            base_dir = Path.cwd()
        elif isinstance(base_dir, str):
            base_dir = Path(base_dir)
        
        # Regular expression to find image references in markdown
        img_pattern = r'!\[(.*?)\]\((.*?)\)'
        
        def replace_image(match):
            alt_text, img_path = match.groups()
            
            # Skip URLs - don't try to embed remote images
            if img_path.startswith(('http://', 'https://', 'data:')):
                return match.group(0)
            
            # Handle relative paths
            if not Path(img_path).is_absolute():
                img_path = base_dir / img_path
            
            try:
                base64_data = self.encode_image_base64(img_path)
                if base64_data:
                    return f'![{alt_text}]({base64_data})'
                else:
                    return match.group(0)  # Return original if encoding failed
            except Exception:
                return match.group(0)  # Return original on error
        
        return re.sub(img_pattern, replace_image, md_content)
    
    def format_meta_html(self, meta):
        """Format metadata as HTML for the report."""
        meta_html = ""
        rendered_keys = set()
        for k in FIELD_ORDER:
            if k not in meta:
                continue
            rendered_keys.add(k)
            if k in EXCLUDED_KEYS:
                continue
            v = meta[k]
            label = f"<strong>{k.title()}:</strong>"
            # Handle verdict specially
            if k == "verdict":
                verdict_lower = str(v).lower() if v else "unknown"
                css_class = (
                    "verdict verdict-malicious" if "malicious" in verdict_lower else
                    "verdict verdict-benign" if "benign" in verdict_lower else
                    "verdict verdict-unknown"
                )
                meta_html += f'<div>{label} <span class="{css_class}">{v}</span></div>'
            
            # Handle TLP specially
            elif k == "tlp":
                tlp = str(v).upper() if v else ""
                tlp_class_map = {
                    "RED": "tlp tlp-red",
                    "AMBER": "tlp tlp-amber",
                    "GREEN": "tlp tlp-green",
                    "CLEAR": "tlp tlp-clear"
                }
                tlp_class = tlp_class_map.get(tlp, "")
                if tlp_class:
                    meta_html += f'<div><strong>TLP:</strong> <span class="{tlp_class}">{tlp}</span></div>'
                else:
                    meta_html += f"<div>{label} {v}</div>"
            
            # Handle dates specially to format them
            elif k in ["date", "analysis_date"] and v:
                try:
                    if isinstance(v, str):
                        # Try to parse and format date string
                        date_obj = datetime.strptime(v, "%Y-%m-%d")
                        formatted_date = date_obj.strftime("%B %d, %Y")
                        meta_html += f"<div>{label} {formatted_date}</div>"
                    else:
                        meta_html += f"<div>{label} {v}</div>"
                except:
                    # If date parsing fails, use as-is
                    meta_html += f"<div>{label} {v}</div>"
            else:
                meta_html += f"<div>{label} {meta[k]}</div>"
        
        # render any other meta data not found in FIELD_ORDER
        for k, v in meta.items():
            if k in rendered_keys:
                continue
            label = f"<strong>{k.title()}:</strong>"
            meta_html += f"<div>{label} {v}</div>"
        return meta_html
    
    def format_tags_html(self, tags):
        """Format tags as HTML for the report."""
        if not tags:
            return ""
            
        # Normalize tags to list
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        elif not isinstance(tags, list):
            return ""
        
        return "".join(f'<span class="tag">{tag.strip()}</span>' for tag in tags)
    
    def get_tlp_class(self, tlp):
        """Get CSS class for TLP indicator."""
        tlp = str(tlp).upper() if tlp else ""
        tlp_class_map = {
            "RED": "tlp-red",
            "AMBER": "tlp-amber",
            "GREEN": "tlp-green",
            "CLEAR": "tlp-clear"
        }
        return tlp_class_map.get(tlp, "")
    
    def preview_html(self):
        """Generate and preview HTML report in a separate window."""
        try:
            html_content = self._generate_html()
            if not html_content:
                return
                
            # Create temporary file and open in default browser
            temp_dir = Path(os.environ.get('TEMP', '/tmp'))
            temp_file = temp_dir / f"report_preview_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
            
            temp_file.write_text(html_content, encoding="utf-8")
            
            # Open in browser
            import webbrowser
            webbrowser.open(temp_file.as_uri())
            
            self.status_var.set(f"Preview opened in browser: {temp_file}")
        except Exception as e:
            messagebox.showerror("Preview Error", f"Failed to generate preview:\n{e}")
    
    def _generate_html(self):
        """Generate HTML report from markdown content."""
        raw_md = self.body_text.get("1.0", tk.END).strip()
        if not raw_md:
            messagebox.showwarning("Warning", "No content to generate report from.")
            return None
            
        try:
            meta, content_md = self.parse_frontmatter(raw_md)
            content_md = re.sub(r"\\(#+)", r"\1", content_md) # fix broken headers...might break stuff
            # Process inline images
            content_md = self.process_inline_images(content_md)
            
            # Pull key metadata values
            title = str(meta.get("title", "Untitled Report"))
            tags = meta.get("tags", [])
            if tags is None:
                tags = []
                
            tlp = str(meta.get("tlp", "")).upper()
            tlp_class = self.get_tlp_class(tlp)
            
            # Format tags
            tag_html = self.format_tags_html(tags)
            
            # Format meta section
            meta_html = self.format_meta_html(meta)
            
            # Convert markdown body to HTML
            pygments_css = HtmlFormatter(style=self.settings.get("style", "default")).get_style_defs('.codehilite')
            content_html = markdown.markdown(
                content_md,
                extensions=["extra", "tables", "fenced_code", "codehilite", "sane_lists", "nl2br"] #"nl2br"
            )
            
            # Handle logo embedding from settings path
            logo_data = ""
            logo_path = self.settings.get("logo_path", "")
            if logo_path:
                try:
                    # Try to resolve logo path (absolute or relative to script dir)
                    script_dir = Path(__file__).parent.resolve()
                    if Path(logo_path).is_absolute():
                        logo_file_path = Path(logo_path)
                    else:
                        logo_file_path = (script_dir / logo_path).resolve()
                        
                    if logo_file_path.exists():
                        logo_data = self.encode_image_base64(logo_file_path)
                    else:
                        self.status_var.set(f"Warning: Logo file not found: {logo_file_path}")
                except Exception as e:
                    self.status_var.set(f"Warning: Error processing logo: {e}")
            
            # Current date for the report
            current_date = datetime.now().strftime("%B %d, %Y")
            
            # Render the final HTML using Jinja2 template
            html = self.template.render(
                title=title,
                tag_html=tag_html,
                meta_html=meta_html,
                content_html=content_html,
                font=self.settings.get("font", "Arial, sans-serif"),
                margin=self.settings.get("margin", "1.5cm"),
                pygments_css=pygments_css,
                logo_path=logo_data,
                tlp=tlp,
                tlp_class=tlp_class,
                generation_date=current_date
            )
            
            return html
        except Exception as e:
            raise Exception(f"HTML generation failed: {e}")
    
    def generate_report(self):
        """Generate the HTML and PDF report based on markdown + YAML frontmatter."""
        try:
            html = self._generate_html()
            if not html:
                return
                
            # Prompt for output path
            output_base = filedialog.asksaveasfilename(
                defaultextension=".pdf", 
                filetypes=[("PDF files", "*.pdf")]
            )
            if not output_base:
                return
                
            html_path = Path(output_base).with_suffix(".html")
            pdf_path = Path(output_base).with_suffix(".pdf")
            
            # Save HTML and export PDF
            html_path.write_text(html, encoding="utf-8")
            
            self.status_var.set("Generating PDF... Please wait.")
            self.root.update_idletasks()
            
            HTML(string=html, base_url=html_path.parent).write_pdf(str(pdf_path))
            
            self.status_var.set(f"Report exported successfully to {pdf_path}")
            messagebox.showinfo("Success", f"Exported to:\n{html_path}\n{pdf_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report:\n{e}")
            self.status_var.set("Report generation failed")
    
    def show_settings(self):
        """Show settings dialog."""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("400x300")
        settings_window.transient(self.root)
        settings_window.resizable(False, False)
        # Center the settings window over the root
        settings_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (settings_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (settings_window.winfo_height() // 2)
        settings_window.geometry(f"+{x}+{y}")
        settings_frame = tk.Frame(settings_window, padx=15, pady=15)
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        # Font settings
        tk.Label(settings_frame, text="Font:").grid(row=0, column=0, sticky="w", pady=5)
        font_var = tk.StringVar(value=self.settings.get("font", "Arial, sans-serif"))
        font_entry = tk.Entry(settings_frame, textvariable=font_var, width=30)
        font_entry.grid(row=0, column=1, sticky="ew", pady=5)
        
        # Margin settings
        tk.Label(settings_frame, text="Margin:").grid(row=1, column=0, sticky="w", pady=5)
        margin_var = tk.StringVar(value=self.settings.get("margin", "1.5cm"))
        margin_entry = tk.Entry(settings_frame, textvariable=margin_var, width=30)
        margin_entry.grid(row=1, column=1, sticky="ew", pady=5)
        
        # Code style settings
        tk.Label(settings_frame, text="Code Style:").grid(row=2, column=0, sticky="w", pady=5)
        style_var = tk.StringVar(value=self.settings.get("style", "default"))
        style_options = ["default", "emacs", "friendly", "colorful", "vs", "monokai"]
        style_dropdown = tk.OptionMenu(settings_frame, style_var, *style_options)
        style_dropdown.grid(row=2, column=1, sticky="ew", pady=5)
        
        # Logo path settings
        tk.Label(settings_frame, text="Logo:").grid(row=3, column=0, sticky="w", pady=5)
        logo_frame = tk.Frame(settings_frame)
        logo_frame.grid(row=3, column=1, sticky="ew", pady=5)
        
        logo_var = tk.StringVar(value=self.settings.get("logo_path", ""))
        logo_entry = tk.Entry(logo_frame, textvariable=logo_var, width=22)
        logo_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def browse_logo():
            path = filedialog.askopenfilename(filetypes=[
                ("Image files", "*.png;*.jpg;*.jpeg;*.gif;*.svg;*.webp")
            ])
            if path:
                # Make path relative to script directory if possible
                script_dir = Path(__file__).parent.resolve()
                try:
                    rel_path = Path(path).relative_to(script_dir)
                    logo_var.set(str(rel_path))
                except ValueError:
                    # If path can't be made relative, use absolute path
                    logo_var.set(path)
        
        tk.Button(logo_frame, text="...", command=browse_logo, width=3).pack(side=tk.RIGHT)
        
        # Buttons
        button_frame = tk.Frame(settings_window)
        button_frame.pack(fill=tk.X, pady=10)
        
        def save_settings():
            self.settings["font"] = font_var.get()
            self.settings["margin"] = margin_var.get()
            self.settings["style"] = style_var.get()
            self.settings["logo_path"] = logo_var.get()
            
            self._save_settings()
            self.status_var.set("Settings saved")
            settings_window.destroy()
        
        tk.Button(button_frame, text="Cancel", command=settings_window.destroy).pack(side=tk.RIGHT, padx=5)
        tk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT, padx=5)
    
    def show_about(self):
        """Show about dialog."""
        about_window = tk.Toplevel(self.root)
        about_window.title("About")
        about_window.geometry("400x200")
        about_window.transient(self.root)
        about_window.resizable(False, False)
        
        # Center the about window over the root
        about_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (about_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (about_window.winfo_height() // 2)
        about_window.geometry(f"+{x}+{y}")

        about_frame = tk.Frame(about_window, padx=20, pady=20)
        about_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(
            about_frame, 
            text="Malware Analysis Report Generator v1",
            font=("Helvetica", 14, "bold")
        ).pack(pady=(0, 10))
        
        tk.Label(
            about_frame,
            text="This tool generates formatted HTML and PDF reports\n"
                 "from Markdown with YAML frontmatter.",
            justify=tk.CENTER
        ).pack(pady=5)
        
        tk.Label(
            about_frame,
            text=f"© {datetime.now().year}",
            justify=tk.CENTER
        ).pack(pady=(10, 0))
        
        tk.Button(about_frame, text="Close", command=about_window.destroy).pack(pady=(10, 0))


def main():
    """Launch the Tkinter GUI."""
    root = tk.Tk()
    app = ReportGenerator(root)
    
    # Set window size and position
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = min(1000, screen_width - 100)
    window_height = min(700, screen_height - 100)
    
    # Center the window
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    # Create temp directory if it doesn't exist
    temp_dir = Path(os.environ.get('TEMP', '/tmp'))
    if not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)
        
    root.mainloop()


if __name__ == "__main__":
    main()
