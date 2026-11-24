import { ChevronDown, Search, type LucideIcon } from 'lucide-react';
import type { InputHTMLAttributes, SelectHTMLAttributes } from 'react';

type FieldLabel = { label: string; hideLabel?: boolean };

export function SearchField({ label, hideLabel, ...input }: FieldLabel & Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  return <label className="list-field list-search">
    <span className={hideLabel ? 'sr-only' : 'field-label'}>{label}</span>
    <span className="list-field-control">
      <Search aria-hidden="true"/>
      <input {...input} type="search"/>
    </span>
  </label>;
}

export function SelectField({ label, hideLabel, icon: Icon, children, ...select }: FieldLabel & { icon: LucideIcon } & SelectHTMLAttributes<HTMLSelectElement>) {
  return <label className="list-field">
    <span className={hideLabel ? 'sr-only' : 'field-label'}>{label}</span>
    <span className="list-field-control">
      <Icon aria-hidden="true"/>
      <select {...select}>{children}</select>
      <ChevronDown className="field-chevron" aria-hidden="true"/>
    </span>
  </label>;
}
