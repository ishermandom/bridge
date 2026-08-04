// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Shared four-color-deck rendering: suit glyphs, per-suit color classes
// (see styles.css), and helpers to render card codes and server prose
// with their suits colored.

export const SUIT_GLYPHS: Record<string, string> = {
  S: '♠',
  H: '♥',
  D: '♦',
  C: '♣',
};

// The CSS class carrying a suit's deck color, from its code letter.
export function suitClass(suitLetter: string): string {
  return `suit-${suitLetter}`;
}

// A card code ('SA') as colored inline text: ♠A.
export function CardText({ code }: { code: string }) {
  const rank = code[1] === 'T' ? '10' : code[1];
  return (
    <span className={suitClass(code[0])}>
      {SUIT_GLYPHS[code[0]]}
      {rank}
    </span>
  );
}

// A card token in prose: a suit glyph plus an optional rank right after it.
const CARD_TOKEN = /([♠♥♦♣](?:10|[2-9TJQKA])?)/;

const GLYPH_TO_LETTER: Record<string, string> = {
  '♠': 'S',
  '♥': 'H',
  '♦': 'D',
  '♣': 'C',
};

// Server prose (error messages, summaries) with its card tokens colored.
export function GlyphText({ text }: { text: string }) {
  const parts = text.split(CARD_TOKEN);
  return (
    <>
      {parts.map((part, index) => {
        const letter = GLYPH_TO_LETTER[part[0]];
        return letter ? (
          <span key={index} className={suitClass(letter)}>
            {part}
          </span>
        ) : (
          part
        );
      })}
    </>
  );
}
