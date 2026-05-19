import type { PatchEncoder } from '../lib/api';

const OPTIONS: { value: PatchEncoder; label: string }[] = [
  { value: 'uni_v1', label: 'uni_v1' },
  { value: 'uni_v2', label: 'uni_v2' },
  { value: 'phikon', label: 'phikon' },
  { value: 'phikon_v2', label: 'phikon_v2' },
];

interface Props {
  value: PatchEncoder;
  onChange: (value: PatchEncoder) => void;
  id?: string;
}

export default function EncoderSelect({ value, onChange, id }: Props) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as PatchEncoder)}
      className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
    >
      {OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

export function patchSizeFor(encoder: PatchEncoder): number {
  return encoder === 'phikon' || encoder === 'phikon_v2' ? 224 : 256;
}
