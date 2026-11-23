import { createLucideIcon } from "lucide-react"

/**
 * NetAudio Monitor app icon as a Lucide-style glyph, used in the sidebar tile.
 * The full-colour icon is public/icon.svg (the favicon) and docs/images/icon.svg.
 */
export const BrandIcon = createLucideIcon("netaudio", [["path", {"d": "M4 4v16"}], ["path", {"d": "M4 7h9"}], ["path", {"d": "M4 12h14"}], ["path", {"d": "M4 17h6"}], ["circle", {"cx": "16.5", "cy": "7", "r": "1.3"}], ["circle", {"cx": "20.5", "cy": "12", "r": "1.3"}], ["circle", {"cx": "13.5", "cy": "17", "r": "1.3"}]])

/** Classes for the sidebar tile behind the glyph. */
export const brandTile = "bg-blue-500 text-white"
