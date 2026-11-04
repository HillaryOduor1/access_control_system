# core/tokens.py
"""
Primitive, semantic, and component design tokens.

Three-layer token architecture:
  PRIMITIVES  ->  raw scales (color, space, radius, font, control)
  SEMANTIC    ->  role-based tokens built from primitives
  COMPONENT   ->  per-component tokens built from semantic tokens

Light mode contrast

Light background is slate.100 (#F1F5F9), surface is white (#FFFFFF).
This creates a visible 2-step separation between the page and cards /
sidebar. Borders use slate.300 (#CBD5E1). Muted text uses slate.600
(#475569) so small captions and group labels remain readable.
"""

from __future__ import annotations
from typing import Dict


# PRIMITIVE TOKENS

PRIMITIVES: Dict[str, Dict] = {
    "color": {
        "green": {
            "50":  "#DCFCE7",
            "100": "#BBF7D0",
            "500": "#006B3F",
            "600": "#005633",
            "700": "#008C52",
        },
        "slate": {
            "50":  "#F8FAFC",
            "100": "#F1F5F9",
            "200": "#E2E8F0",
            "300": "#CBD5E1",
            "400": "#94A3B8",
            "500": "#64748B",
            "600": "#475569",
            "700": "#334155",
            "800": "#1E293B",
            "900": "#0F172A",
            "950": "#0B1220",
        },
        "red": {
            "50":  "#FEE2E2",
            "500": "#DC2626",
            "600": "#B91C1C",
        },
        "amber": {
            "50":  "#FEF3C7",
            "500": "#D97706",
            "700": "#92400E",
        },
        "emerald": {
            "50":  "#D1FAE5",
            "500": "#059669",
            "700": "#065F46",
        },
        "blue": {
            "50":  "#DBEAFE",
            "500": "#2563EB",
            "700": "#1E40AF",
        },
        "white": "#FFFFFF",
        "black": "#000000",
    },
    "space": {
        "0":  0,
        "1":  4,
        "2":  8,
        "3":  12,
        "4":  16,
        "5":  20,
        "6":  24,
        "7":  28,
        "8":  32,
        "10": 40,
        "12": 48,
        "16": 64,
    },
    "radius": {
        "none": 0,
        "sm":   4,
        "md":   6,
        "lg":   10,
        "xl":   14,
        "full": 9999,
    },
    "font": {
        "size": {
            "display": 32,
            "h1":      28,
            "h2":      22,
            "h3":      18,
            "h4":      15,
            "body":    13,
            "small":   12,
            "caption": 11,
        },
        "weight": {
            "normal":   400,
            "medium":   500,
            "semibold": 600,
            "bold":     700,
        },
        "line_height": {
            "tight": 1.2,
            "normal": 1.5,
            "relaxed": 1.7,
        },
    },
    "control": {
        "height": {
            "sm":     28,
            "md":     34,
            "lg":     42,
        },
        "padding": {
            "sm": (4, 8),
            "md": (6, 10),
            "lg": (8, 12),
        },
    },
    "scrollbar": {
        "size":  10,
        "radius": 5,
    },
}


# SEMANTIC TOKENS

def _dark_semantic(c: Dict) -> Dict[str, str]:
    """Dark theme palette (unchanged — dark mode already reads well)."""
    return {
        "background":             c["slate"]["950"],
        "surface":                c["slate"]["800"],
        "surface-hover":          c["slate"]["700"],
        "surface-active":         c["slate"]["600"],
        "popover":                c["slate"]["800"],
        "popover-foreground":     c["slate"]["50"],
        "foreground":             c["slate"]["50"],
        "foreground-secondary":   c["slate"]["300"],
        "muted-foreground":       c["slate"]["400"],
        "text_on_primary":        c["white"],
        "primary":                c["green"]["500"],
        "primary-hover":          c["green"]["700"],
        "primary-subtle":         "#0A2E1A",
        "primary-foreground":     c["white"],
        "destructive":            c["red"]["500"],
        "destructive-hover":      c["red"]["600"],
        "destructive-subtle":     "#3F1A1A",
        "destructive-foreground": c["white"],
        "warning":                c["amber"]["500"],
        "warning-subtle":         "#3F2A0A",
        "warning-foreground":     "#FBBF24",
        "success":                c["emerald"]["500"],
        "success-subtle":         "#0A2E1A",
        "success-foreground":     "#34D399",
        "info":                   c["blue"]["500"],
        "info-subtle":            "#1A2A4F",
        "info-foreground":        "#60A5FA",
        "secondary":              c["slate"]["700"],
        "secondary-foreground":   c["slate"]["50"],
        "muted":                  c["slate"]["800"],
        "accent":                 c["slate"]["700"],
        "accent-foreground":      c["slate"]["50"],
        "border":                 c["slate"]["700"],
        "border-strong":          c["slate"]["500"],
        "input":                  c["slate"]["800"],
        "ring":                   c["green"]["700"],
        "card":                   c["slate"]["800"],
        "card-foreground":        c["slate"]["50"],
        "scrollbar_track":        c["slate"]["800"],
        "scrollbar_handle":       c["slate"]["500"],
        "scrollbar_handle_hover": c["slate"]["400"],
    }


def _light_semantic(c: Dict) -> Dict[str, str]:
    """
    Light theme palette tuned for contrast.

    Key differences vs the previous version:
      - background is slate.100 (#F1F5F9) not slate.50, so white cards
        and the sidebar visually separate from the page.
      - muted-foreground is slate.600 (#475569) not slate.500.
      - border is slate.300 (#CBD5E1) not slate.200.
      - primary-subtle is green.50 (#DCFCE7) with a stronger tint.
    """
    return {
        "background":             c["slate"]["100"],     # #F1F5F9
        "surface":                c["white"],            # #FFFFFF
        "surface-hover":          c["slate"]["200"],     # #E2E8F0
        "surface-active":         c["slate"]["300"],     # #CBD5E1
        "popover":                c["white"],
        "popover-foreground":     c["slate"]["900"],
        "foreground":             c["slate"]["900"],     # #0F172A
        "foreground-secondary":   c["slate"]["700"],     # #334155
        "muted-foreground":       c["slate"]["600"],     # #475569
        "text_on_primary":        c["white"],
        "primary":                c["green"]["500"],
        "primary-hover":          c["green"]["600"],
        "primary-subtle":         c["green"]["50"],      # #DCFCE7
        "primary-foreground":     c["white"],
        "destructive":            c["red"]["500"],       # #DC2626
        "destructive-hover":      c["red"]["600"],
        "destructive-subtle":     c["red"]["50"],
        "destructive-foreground": c["white"],
        "warning":                c["amber"]["500"],
        "warning-subtle":         c["amber"]["50"],
        "warning-foreground":     c["amber"]["700"],
        "success":                c["emerald"]["500"],
        "success-subtle":         c["emerald"]["50"],
        "success-foreground":     c["emerald"]["700"],
        "info":                   c["blue"]["500"],
        "info-subtle":            c["blue"]["50"],
        "info-foreground":        c["blue"]["700"],
        "secondary":              c["slate"]["200"],     # #E2E8F0
        "secondary-foreground":   c["slate"]["900"],
        "muted":                  c["slate"]["200"],     # #E2E8F0
        "accent":                 c["slate"]["300"],     # #CBD5E1
        "accent-foreground":      c["slate"]["900"],
        "border":                 c["slate"]["300"],     # #CBD5E1
        "border-strong":          c["slate"]["500"],     # #64748B
        "input":                  c["white"],
        "ring":                   c["green"]["500"],
        "card":                   c["white"],
        "card-foreground":        c["slate"]["900"],
        "scrollbar_track":        c["slate"]["200"],
        "scrollbar_handle":       c["slate"]["400"],
        "scrollbar_handle_hover": c["slate"]["500"],
    }


def build_semantic(
    theme: str,
    density: str = "comfortable",
    radius_key: str = "medium",
    high_contrast: bool = False,
    font_size: int = 13,
) -> Dict:
    c = PRIMITIVES["color"]
    base = _dark_semantic(c) if theme == "dark" else _light_semantic(c)

    density_map = {
        "compact":     {"control_height": 28, "padding_vertical": 4,
                        "padding_horizontal": 8,  "section_spacing": 10},
        "comfortable": {"control_height": 34, "padding_vertical": 6,
                        "padding_horizontal": 10, "section_spacing": 14},
        "spacious":    {"control_height": 40, "padding_vertical": 8,
                        "padding_horizontal": 12, "section_spacing": 18},
    }
    density_values = density_map.get(density, density_map["comfortable"])

    radius_map = {
        "small":  {"radius": "4px",  "radius-sm": "3px",  "radius-lg": "7px",  "radius-xl": "10px"},
        "medium": {"radius": "6px",  "radius-sm": "4px",  "radius-lg": "10px", "radius-xl": "14px"},
        "large":  {"radius": "10px", "radius-sm": "7px",  "radius-lg": "14px", "radius-xl": "18px"},
    }
    radius_values = radius_map.get(radius_key, radius_map["medium"])

    typo = {
        "font.display": max(20, font_size + 16),
        "font.h1":      max(18, font_size + 12),
        "font.h2":      max(16, font_size + 8),
        "font.h3":      max(15, font_size + 4),
        "font.h4":      max(14, font_size + 2),
        "font.body":    font_size,
        "font.small":   max(11, font_size - 1),
        "font.caption": max(10, font_size - 2),
    }

    spacing = {f"space.{k}": v for k, v in PRIMITIVES["space"].items()}

    tokens: Dict = {
        **base,
        **density_values,
        **radius_values,
        **typo,
        **spacing,
        "scrollbar_size":   PRIMITIVES["scrollbar"]["size"],
        "scrollbar_radius": PRIMITIVES["scrollbar"]["radius"],
        "font_size":        font_size,
    }

    tokens.update({
        "bg_primary":       tokens["background"],
        "bg_secondary":     tokens["muted"],
        "text_primary":     tokens["foreground"],
        "text_secondary":   tokens["foreground-secondary"],
        "text_muted":       tokens["muted-foreground"],
        "primary_hover":    tokens["primary-hover"],
        "accent_color":     tokens["accent"],
        "error":            tokens["destructive"],
        "surface_hover":    tokens["surface-hover"],
    })

    if high_contrast:
        if theme == "light":
            tokens.update({
                "background": "#FFFFFF", "surface": "#FFFFFF",
                "foreground": "#000000", "foreground-secondary": "#111111",
                "muted-foreground": "#333333", "border": "#000000",
                "border-strong": "#000000",
                "scrollbar_track": "#E5E7EB",
                "scrollbar_handle": "#000000",
                "scrollbar_handle_hover": "#111111",
                "ring": "#000000",
            })
        else:
            tokens.update({
                "background": "#000000", "surface": "#000000",
                "foreground": "#FFFFFF", "foreground-secondary": "#FFFFFF",
                "muted-foreground": "#E5E7EB", "border": "#FFFFFF",
                "border-strong": "#FFFFFF",
                "scrollbar_track": "#111111",
                "scrollbar_handle": "#FFFFFF",
                "scrollbar_handle_hover": "#E5E7EB",
                "ring": "#FFFFFF",
            })

    return tokens


# COMPONENT TOKENS

def build_components(semantic: Dict) -> Dict:
    return {
        "button.primary.background":        semantic["primary"],
        "button.primary.background.hover":  semantic["primary-hover"],
        "button.primary.text":              semantic["primary-foreground"],
        "button.primary.radius":            semantic["radius"],
        "button.primary.height":            semantic["control_height"],
        "button.primary.padding_x":         semantic["padding_horizontal"],

        "button.destructive.background":       semantic["destructive"],
        "button.destructive.background.hover": semantic["destructive-hover"],
        "button.destructive.text":             semantic["destructive-foreground"],

        "button.outline.background":       "transparent",
        "button.outline.background.hover": semantic["surface-hover"],
        "button.outline.border":           semantic["border"],
        "button.outline.text":             semantic["foreground"],

        "input.background":       semantic["input"],
        "input.border":           semantic["border"],
        "input.border.hover":     semantic["border-strong"],
        "input.border.focus":     semantic["ring"],
        "input.radius":           semantic["radius"],
        "input.height":           semantic["control_height"],
        "input.padding_v":        semantic["padding_vertical"],
        "input.padding_h":        semantic["padding_horizontal"],

        "card.background":        semantic["card"],
        "card.border":            semantic["border"],
        "card.radius":            semantic["radius-lg"],
        "card.padding":           semantic["section_spacing"],

        "dialog.background":      semantic["surface"],
        "dialog.border":          semantic["border"],
        "dialog.radius":          semantic["radius-xl"],
        "dialog.min_width":       420,

        "table.header.background": semantic["muted"],
        "table.header.text":       semantic["muted-foreground"],
        "table.row.border":        semantic["border"],
        "table.row.hover":         semantic["surface-hover"],
        "table.row.selected":      semantic["primary-subtle"],
        "table.row.selected.text": semantic["primary"],
        "table.row.height":        44,

        "focus.ring":             semantic["ring"],
        "focus.width":            "2px",
    }