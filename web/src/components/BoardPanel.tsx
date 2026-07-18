import { useMemo, useState } from "react";
import { Chessboard, type ChessboardOptions } from "react-chessboard";

import type { WorkspaceSnapshot } from "../types/workspace";

interface BoardPanelProps {
  workspace: WorkspaceSnapshot;
  pending: boolean;
  hintMoveUci: string | null;
  onMove: (uci: string) => void;
  selectedPieceRef: string | null;
  onInspectPiece: (pieceRef: string) => void;
  targetPicking: boolean;
  pickedTarget: string | null;
  onPickTarget: (square: string) => void;
}

export function BoardPanel({
  workspace,
  pending,
  hintMoveUci,
  onMove,
  selectedPieceRef,
  onInspectPiece,
  targetPicking,
  pickedTarget,
  onPickTarget,
}: BoardPanelProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [promotionMoves, setPromotionMoves] = useState<string[]>([]);
  const legalMoves = workspace.position.legalMovesUci;
  const enabled = !pending && legalMoves.length > 0;
  const legalSources = useMemo(() => new Set(legalMoves.map((move) => move.slice(0, 2))), [legalMoves]);
  const legalTargets = selected
    ? legalMoves.filter((move) => move.startsWith(selected)).map((move) => move.slice(2, 4))
    : [];
  const squareStyles: Record<string, React.CSSProperties> = {};
  if (workspace.position.lastMoveUci) {
    squareStyles[workspace.position.lastMoveUci.slice(0, 2)] = { background: "#899665" };
    squareStyles[workspace.position.lastMoveUci.slice(2, 4)] = { background: "#a8b57a" };
  }
  if (hintMoveUci) {
    squareStyles[hintMoveUci.slice(0, 2)] = {
      ...squareStyles[hintMoveUci.slice(0, 2)],
      background: "#e2ad55",
      boxShadow: "inset 0 0 0 5px #fff0b3",
    };
  }
  if (selected) squareStyles[selected] = { boxShadow: "inset 0 0 0 4px #e2ad55" };
  const inspected = workspace.startingPieces.find((piece) => piece.ref === selectedPieceRef);
  if (inspected?.currentSquare) {
    squareStyles[inspected.currentSquare] = {
      ...squareStyles[inspected.currentSquare],
      boxShadow: "inset 0 0 0 5px #61c7c2",
    };
  }
  if (pickedTarget) {
    squareStyles[pickedTarget] = {
      ...squareStyles[pickedTarget],
      boxShadow: "inset 0 0 0 5px #d6a44e",
    };
  }
  legalTargets.forEach((square) => {
    squareStyles[square] = {
      ...squareStyles[square],
      boxShadow: "inset 0 0 0 5px rgba(29, 93, 67, 0.75)",
    };
  });

  const chooseMove = (source: string, target: string | null) => {
    if (!target) return false;
    const candidates = legalMoves.filter((move) => move.startsWith(`${source}${target}`));
    if (candidates.length === 1) {
      setSelected(null);
      onMove(candidates[0]);
      return true;
    }
    if (candidates.length > 1) {
      setPromotionMoves(candidates);
      return false;
    }
    return false;
  };

  const options: ChessboardOptions = {
    id: "development-board",
    position: workspace.position.fen,
    boardOrientation: workspace.flow.side,
    boardStyle: { borderRadius: "8px", boxShadow: "0 18px 50px rgba(0, 0, 0, 0.28)" },
    darkSquareStyle: { backgroundColor: "#66734b" },
    lightSquareStyle: { backgroundColor: "#d8d2b0" },
    squareStyles,
    allowDragging: enabled && !targetPicking,
    showNotation: true,
    canDragPiece: ({ square }) => Boolean(square && legalSources.has(square)),
    onPieceDrop: ({ sourceSquare, targetSquare }) => chooseMove(sourceSquare, targetSquare),
    onSquareClick: ({ square }) => {
      if (targetPicking) {
        setSelected(null);
        onPickTarget(square);
        return;
      }
      const piece = workspace.startingPieces.find((item) => item.currentSquare === square);
      if (piece) onInspectPiece(piece.ref);
      if (!enabled) return;
      if (selected && chooseMove(selected, square)) return;
      setSelected(legalSources.has(square) ? square : null);
    },
    squareRenderer: ({ square, children }) => {
      const startingPiece = workspace.startingPieces.find(
        (item) =>
          item.currentSquare === square
          && item.state === "undeveloped"
          && item.color === workspace.flow.side,
      );
      const marker = startingPiece ? developmentMarker(startingPiece) : null;
      return (
        <div className="piece-square-layer">
          {children}
          {marker && (
            <span
              className={`development-marker marker-${marker.status}`}
              role="img"
              aria-label={marker.label}
              title={marker.label}
            >
              {marker.icon}
            </span>
          )}
        </div>
      );
    },
  };

  return (
    <section className="board-column" aria-label="Chessboard">
      <div className="board-shell" aria-label="Interactive chessboard">
        <Chessboard options={options} />
      </div>
      <p className="sr-status" aria-live="polite">
        {targetPicking
          ? "Target selection is active. Choose a target square."
          : pending ? "Submitting move" : `${workspace.phase.replaceAll("-", " ")}. ${legalMoves.length} legal moves.`}
      </p>
      {promotionMoves.length > 0 && (
        <div className="promotion-picker" role="dialog" aria-label="Choose promotion piece">
          <strong>Promote to</strong>
          <div className="button-row">
            {promotionMoves.map((move) => (
              <button key={move} onClick={() => { setPromotionMoves([]); setSelected(null); onMove(move); }}>
                {promotionName(move.at(-1) ?? "q")}
              </button>
            ))}
            <button onClick={() => setPromotionMoves([])}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}

function developmentMarker(piece: WorkspaceSnapshot["startingPieces"][number]) {
  const rule = piece.developmentRules[0] ?? null;
  if (!rule) {
    return { icon: "+", status: "unassigned", label: `${piece.label}. No development rule assigned.` };
  }
  const icon = {
    inactive: "○",
    applicable: "●",
    selected: "★",
    waiting: "!",
    developed: "·",
    captured: "×",
    "out-of-scope": "◇",
  }[rule.status];
  return {
    icon,
    status: rule.status,
    label: `${piece.label}. Development rule ${rule.status}. Target ${rule.target}. ${rule.reason}`,
  };
}

function promotionName(piece: string): string {
  return ({ q: "Queen", r: "Rook", b: "Bishop", n: "Knight" } as Record<string, string>)[piece] ?? piece;
}
