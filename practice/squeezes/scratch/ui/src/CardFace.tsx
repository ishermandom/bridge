// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// One card rendered as a clickable face; the suit glyph and color derive
// from the two-character card code (`SA`, `H7`).

const SUIT_GLYPHS: Record<string, string> = {
  S: '♠',
  H: '♥',
  D: '♦',
  C: '♣',
};

interface CardFaceProps {
  code: string;
  playable: boolean;
  onPlay?: (code: string) => void;
}

// TODO(ilya): learning exercise — make the card faces look like cards:
// corner indices, a hover lift for playable cards, maybe a small deal-in
// animation. Everything is contained in this component plus `.card` rules
// in styles.css.
export default function CardFace({ code, playable, onPlay }: CardFaceProps) {
  const suit = code[0];
  const rank = code[1] === 'T' ? '10' : code[1];
  const isRed = suit === 'H' || suit === 'D';
  return (
    <button
      className={`card ${isRed ? 'red' : 'black'}`}
      disabled={!playable}
      onClick={() => onPlay?.(code)}
    >
      {SUIT_GLYPHS[suit]}
      {rank}
    </button>
  );
}
