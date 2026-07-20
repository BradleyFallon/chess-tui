import type { StructureRuntimeSnapshot } from "../types/workspace";

export function StructureScopePicker({
  structures,
  selected,
  onChange,
}: {
  structures: StructureRuntimeSnapshot[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const scoped = selected.length > 0;
  return (
    <fieldset className="scope-picker">
      <legend>Where does this apply?</legend>
      <label>
        <input
          type="radio"
          checked={!scoped}
          onChange={() => onChange([])}
        />
        Everywhere as a fallback
      </label>
      <label>
        <input
          type="radio"
          checked={scoped}
          disabled={structures.length === 0}
          onChange={() => onChange(structures[0] ? [structures[0].id] : [])}
        />
        In one or more plans
      </label>
      {scoped && (
        <div className="scope-options">
          {structures.map((structure) => (
            <label key={structure.id}>
              <input
                type="checkbox"
                checked={selected.includes(structure.id)}
                onChange={(event) => onChange(
                  event.target.checked
                    ? [...selected, structure.id]
                    : selected.filter((id) => id !== structure.id),
                )}
              />
              {structure.name}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
