import { useMemo, useState } from "react";
import { Chessboard, type ChessboardOptions } from "react-chessboard";

import type { WorkspaceSnapshot } from "../types/workspace";

interface Props {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  selectedAlias: string | null;
  onInspect: (alias: string) => void;
  onMove: (uci: string) => void;
}

export function BoardPanel({ workspace, pending, selectedAlias, onInspect, onMove }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const legal = workspace.position.legalMovesUci;
  const sources = useMemo(() => new Set(legal.map((move) => move.slice(0, 2))), [legal]);
  const targets = selected ? legal.filter((move) => move.startsWith(selected)).map((move) => move.slice(2, 4)) : [];
  const styles: Record<string, React.CSSProperties> = {};
  if (workspace.hintMoveUci) {
    styles[workspace.hintMoveUci.slice(0, 2)] = {
      boxShadow: "inset 0 0 0 5px #e2ad55",
    };
    styles[workspace.hintMoveUci.slice(2, 4)] = {
      boxShadow: "inset 0 0 0 5px rgba(226, 173, 85, .82)",
    };
  }
  const inspected = workspace.pieceScripts.find((piece) => piece.alias === selectedAlias);
  if (inspected?.currentSquare) styles[inspected.currentSquare] = { boxShadow: "inset 0 0 0 5px #61c7c2" };
  if (workspace.position.lastMoveUci) {
    styles[workspace.position.lastMoveUci.slice(0, 2)] = { background: "#899665" };
    styles[workspace.position.lastMoveUci.slice(2, 4)] = { background: "#a8b57a" };
  }
  if (selected) styles[selected] = { boxShadow: "inset 0 0 0 4px #e2ad55" };
  targets.forEach((square) => { styles[square] = { boxShadow: "inset 0 0 0 5px rgba(29, 93, 67, .75)" }; });

  const choose = (from: string, to: string | null) => {
    if (!to) return false;
    const candidates = legal.filter((move) => move.startsWith(`${from}${to}`));
    if (candidates.length !== 1) return false;
    setSelected(null);
    onMove(candidates[0]);
    return true;
  };
  const options: ChessboardOptions = {
    id: "rulebook-board",
    position: workspace.position.fen,
    boardOrientation: workspace.rulebook.side,
    allowDragging: !pending,
    squareStyles: styles,
    darkSquareStyle: { backgroundColor: "#66734b" },
    lightSquareStyle: { backgroundColor: "#d8d2b0" },
    canDragPiece: ({ square }) => Boolean(square && sources.has(square)),
    onPieceDrop: ({ sourceSquare, targetSquare }) => choose(sourceSquare, targetSquare),
    onSquareClick: ({ square }) => {
      const piece = workspace.pieceScripts.find((item) => item.currentSquare === square);
      if (piece) onInspect(piece.alias);
      if (selected && choose(selected, square)) return;
      setSelected(sources.has(square) ? square : null);
    },
  };
  return (
    <section className="board-column" aria-label="Chessboard">
      <div className="board-shell"><Chessboard options={options} /></div>
      <p className="sr-status" aria-live="polite">
        {pending ? "Submitting move" : `${legal.length} legal moves.`}
      </p>
    </section>
  );
}
