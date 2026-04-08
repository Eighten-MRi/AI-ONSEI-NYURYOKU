import tkinter as tk
import tkinter.font as tkfont

class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, radius=8, 
                 bg="#333333", fg="white", active_bg="#555555", active_fg="white", 
                 font=None, padx=16, pady=8, state="normal", disabled_bg="#222222", disabled_fg="#555555",
                 **kwargs):
        # Extract bg for canvas background (transparent-ish)
        canvas_bg = kwargs.pop('bg', parent.cget('bg'))
        
        super().__init__(parent, bg=canvas_bg, highlightthickness=0, borderwidth=0, **kwargs)
        
        self.command = command
        self.text_content = text
        self.radius = radius
        self.btn_bg = bg
        self.btn_fg = fg
        self.active_bg = active_bg
        self.active_fg = active_fg
        self.disabled_bg = disabled_bg
        self.disabled_fg = disabled_fg
        self.pad_x = padx
        self.pad_y = pady
        self.state = state
        
        if font:
            if isinstance(font, tkfont.Font):
                self.font = font
            else:
                self.font = tkfont.Font(font=font)
        else:
            self.font = tkfont.Font(family="Segoe UI", size=10)

        self._calculate_size()
        
        self.shapes = []
        self.text_id = None
        
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Configure>", self._on_resize)
        
        self.draw()

    def _calculate_size(self):
        # Calculate size based on text
        if not self.text_content:
            text_w = 0
            text_h = self.font.metrics("linespace")
        else:
            text_w = self.font.measure(self.text_content)
            text_h = self.font.metrics("linespace")
            
        self.req_width = text_w + (self.pad_x * 2)
        self.req_height = text_h + (self.pad_y * 2)
        # Set requested size, but self.width/height will be determined by actual allocation if packed
        self.width = self.req_width
        self.height = self.req_height
        self.configure(width=self.req_width, height=self.req_height)

    def _on_resize(self, event):
        self.width = event.width
        self.height = event.height
        self.draw()

    def draw(self):
        self.delete("all")
        self.shapes = []
        
        r = self.radius
        w = self.width
        h = self.height
        
        # Prevent negative dimensions
        if w <= 0 or h <= 0: return

        current_bg = self.btn_bg if self.state == "normal" else self.disabled_bg
        current_fg = self.btn_fg if self.state == "normal" else self.disabled_fg
        
        # Draw rounded rect
        self.shapes.append(self.create_oval(0, 0, r*2, r*2, fill=current_bg, outline=""))
        self.shapes.append(self.create_oval(w-r*2, 0, w, r*2, fill=current_bg, outline=""))
        self.shapes.append(self.create_oval(0, h-r*2, r*2, h, fill=current_bg, outline=""))
        self.shapes.append(self.create_oval(w-r*2, h-r*2, w, h, fill=current_bg, outline=""))
        
        self.shapes.append(self.create_rectangle(r, 0, w-r, h, fill=current_bg, outline=""))
        self.shapes.append(self.create_rectangle(0, r, w, h-r, fill=current_bg, outline=""))
        
        # Text
        self.text_id = self.create_text(w/2, h/2, text=self.text_content, fill=current_fg, font=self.font)

    def _on_click(self, event):
        if self.state == "normal" and self.command:
            self.command()

    def _on_enter(self, event):
        if self.state == "normal":
            self._update_color(self.active_bg, self.active_fg)
            self.config(cursor="hand2")

    def _on_leave(self, event):
        if self.state == "normal":
            self._update_color(self.btn_bg, self.btn_fg)
            self.config(cursor="")

    def _update_color(self, bg, fg):
        for shape in self.shapes:
            self.itemconfig(shape, fill=bg)
        self.itemconfig(self.text_id, fill=fg)

    def config(self, **kwargs):
        needs_redraw = False
        needs_resize = False

        if "state" in kwargs:
            self.state = kwargs.pop("state")
            needs_redraw = True
        
        if "text" in kwargs:
            self.text_content = kwargs.pop("text")
            needs_resize = True
            needs_redraw = True
            
        if "bg" in kwargs:
            self.btn_bg = kwargs.pop("bg")
            needs_redraw = True
            
        if "fg" in kwargs:
            self.btn_fg = kwargs.pop("fg")
            needs_redraw = True
            
        if "active_bg" in kwargs:
            self.active_bg = kwargs.pop("active_bg")
            
        if "active_fg" in kwargs:
            self.active_fg = kwargs.pop("active_fg")
            
        if "disabled_bg" in kwargs:
            self.disabled_bg = kwargs.pop("disabled_bg")
            if self.state == "disabled": needs_redraw = True
            
        if "disabled_fg" in kwargs:
            self.disabled_fg = kwargs.pop("disabled_fg")
            if self.state == "disabled": needs_redraw = True

        # 全プロパティを反映したあとで1回だけ描画（毎属性変更ごとに描画する無駄を防ぐ）
        if needs_resize:
            self._calculate_size()
        if needs_redraw:
            self.draw()
        super().config(**kwargs)
        
    def configure(self, **kwargs):
        self.config(**kwargs)


class RoundedEntry(tk.Canvas):
    def __init__(self, parent, width=200, height=30, radius=8, 
                 bg="#333333", fg="white", 
                 insertbackground="white",
                 font=None, textvariable=None, 
                 border_color="gray", border_width=1,
                 **kwargs):
                     
        canvas_bg = kwargs.pop('bg', parent.cget('bg'))
        focus_color = kwargs.pop('focus_color', "#5e6ad2")
        super().__init__(parent, bg=canvas_bg, highlightthickness=0, borderwidth=0, **kwargs)

        self.radius = radius
        self.entry_bg = bg
        self.entry_fg = fg
        self.border_color = border_color
        self.border_width = border_width
        self._original_border_color = border_color
        self.focus_color = focus_color

        self.width = width
        self.height = height
        self.configure(width=self.width, height=self.height)

        if font:
            if isinstance(font, tkfont.Font):
                self.font = font
            else:
                self.font = tkfont.Font(font=font)
        else:
            self.font = tkfont.Font(family="Segoe UI", size=10)

        # Embed Entry
        padding = 4
        
        self.entry = tk.Entry(self, bg=bg, fg=fg, 
                              insertbackground=insertbackground,
                              bd=0, highlightthickness=0, 
                              relief="flat", font=self.font,
                              textvariable=textvariable)
        
        # Create window item
        entry_width = width - (radius*2) - (padding*2)
        if entry_width < 10: entry_width = 10
        
        self.entry_win_id = self.create_window(radius + padding, height/2, window=self.entry, anchor="w", width=entry_width)
        
        # Bind resize
        self.bind("<Configure>", self._on_resize)
        
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        
        self.draw()

    def _on_focus_in(self, event):
        self.border_color = self.focus_color
        self.draw()

    def _on_focus_out(self, event):
        self.border_color = self._original_border_color
        self.draw()

    def _on_resize(self, event):
        self.width = event.width
        self.height = event.height
        
        # Update entry width
        padding = 4
        entry_width = self.width - (self.radius*2) - (padding*2)
        if entry_width > 0:
            self.itemconfigure(self.entry_win_id, width=entry_width)
            self.coords(self.entry_win_id, self.radius + padding, self.height/2)
            
        self.draw()
            
    def draw(self):
        self.delete("shape") # Delete only shapes, keep window
        # Tags are useful here, let's tag shapes
        
        r = self.radius
        w = self.width
        h = self.height
        bw = self.border_width
        bc = self.border_color
        bg = self.entry_bg
        
        if w <= 0 or h <= 0: return

        def draw_pill(x, y, w, h, r, color):
            # Using tag "shape" to easily delete
            self.create_oval(x, y, x+r*2, y+r*2, fill=color, outline="", tags="shape")
            self.create_oval(x+w-r*2, y, x+w, y+r*2, fill=color, outline="", tags="shape")
            self.create_oval(x, y+h-r*2, x+r*2, y+h, fill=color, outline="", tags="shape")
            self.create_oval(x+w-r*2, y+h-r*2, x+w, y+h, fill=color, outline="", tags="shape")
            self.create_rectangle(x+r, y, x+w-r, y+h, fill=color, outline="", tags="shape")
            self.create_rectangle(x, y+r, x+w, y+h-r, fill=color, outline="", tags="shape")

        if bw > 0:
            draw_pill(0, 0, w, h, r, bc)
            draw_pill(bw, bw, w-bw, h-bw, r-bw if r>bw else 0, bg)
        else:
            draw_pill(0, 0, w, h, r, bg)
            
        # Ensure window is on top
        self.tag_lower("shape")


    def get(self):
        return self.entry.get()
        
    def set(self, text):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)
        
    def bind_entry(self, sequence, func, add=None):
        self.entry.bind(sequence, func, add)
