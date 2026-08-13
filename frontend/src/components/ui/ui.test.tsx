import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button, Card, Chip, Field, SectionHeader, StatusPill, inputCls } from './index';

afterEach(cleanup);

describe('StatusPill', () => {
  it('renders the status as its own label when none is given', () => {
    render(<StatusPill status="running" />);
    expect(screen.getByText('running')).toBeTruthy();
  });

  it('humanizes underscores in compound statuses', () => {
    render(<StatusPill status="running_trident" />);
    expect(screen.getByText('running trident')).toBeTruthy();
  });

  it('prefers an explicit label over the raw status', () => {
    render(<StatusPill status="failed" label="Needs attention" />);
    expect(screen.getByText('Needs attention')).toBeTruthy();
    expect(screen.queryByText('failed')).toBeNull();
  });

  it.each([
    ['succeeded', '--s-success'],
    ['ready', '--s-success'],
    ['failed', '--s-failed'],
    ['canceled', '--s-warn'],
    ['queued', '--s-queued'],
    ['pending', '--s-queued'],
    ['running', '--s-running'],
    ['rendering', '--s-rendering'],
    ['running_viz', '--s-rendering'],
  ])('maps %s onto the %s token family', (status, token) => {
    const { container } = render(<StatusPill status={status} />);
    expect(container.firstElementChild?.className).toContain(token);
  });

  it.each(['running', 'running_trident', 'running_viz', 'rendering'])(
    'animates the in-flight status %s',
    (status) => {
      const { container } = render(<StatusPill status={status} />);
      expect(container.firstElementChild?.className).toContain('animate-pulse-slow');
    },
  );

  it.each(['succeeded', 'ready', 'failed', 'canceled', 'queued'])(
    'leaves the settled status %s unanimated',
    (status) => {
      const { container } = render(<StatusPill status={status} />);
      expect(container.firstElementChild?.className).not.toContain('animate-pulse-slow');
    },
  );

  it('falls back to the queued tone for an unrecognized status', () => {
    const { container } = render(<StatusPill status="something_new" />);
    expect(container.firstElementChild?.className).toContain('--s-queued');
  });

  it('appends caller classes without dropping its own', () => {
    const { container } = render(<StatusPill status="ready" className="ml-2" />);
    const cls = container.firstElementChild?.className ?? '';
    expect(cls).toContain('ml-2');
    expect(cls).toContain('rounded-full');
  });
});

describe('Button', () => {
  it('defaults to type=button so it never submits a form by accident', () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole('button').getAttribute('type')).toBe('button');
  });

  it('fires onClick when enabled', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('swallows clicks while disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        Go
      </Button>,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it.each([
    ['primary', 'bg-grad-accent'],
    ['outline', 'border-border-strong'],
    ['ghost', 'bg-transparent'],
    ['danger', '--s-failed-text'],
  ] as const)('applies the %s variant', (variant, marker) => {
    render(<Button variant={variant}>Go</Button>);
    expect(screen.getByRole('button').className).toContain(marker);
  });

  it.each([
    ['sm', 'text-xs'],
    ['md', 'text-sm'],
    ['lg', 'py-2.5'],
  ] as const)('applies the %s size', (size, marker) => {
    render(<Button size={size}>Go</Button>);
    expect(screen.getByRole('button').className).toContain(marker);
  });

  it('defaults to the outline variant at medium size', () => {
    render(<Button>Go</Button>);
    const cls = screen.getByRole('button').className;
    expect(cls).toContain('border-border-strong');
    expect(cls).toContain('px-3.5');
  });

  it('forwards arbitrary button attributes', () => {
    render(
      <Button type="submit" title="tooltip" aria-label="Save">
        Go
      </Button>,
    );
    const btn = screen.getByRole('button');
    expect(btn.getAttribute('type')).toBe('submit');
    expect(btn.getAttribute('title')).toBe('tooltip');
  });
});

describe('Card', () => {
  it('renders its children on the standard surface tokens', () => {
    const { container } = render(<Card>content</Card>);
    const cls = container.firstElementChild?.className ?? '';
    expect(screen.getByText('content')).toBeTruthy();
    expect(cls).toContain('bg-surface');
    expect(cls).toContain('border-border');
    expect(cls).toContain('shadow-card');
  });

  it('adds the lift treatment only when hover is set', () => {
    const { container: plain } = render(<Card>a</Card>);
    const { container: lifted } = render(<Card hover>b</Card>);
    expect(plain.firstElementChild?.className).not.toContain('shadow-card-hover');
    expect(lifted.firstElementChild?.className).toContain('shadow-card-hover');
  });
});

describe('Chip', () => {
  it('renders its children', () => {
    render(<Chip>uni_v1</Chip>);
    expect(screen.getByText('uni_v1')).toBeTruthy();
  });

  it('switches to a monospace face when mono is set', () => {
    const { container: plain } = render(<Chip>a</Chip>);
    const { container: mono } = render(<Chip mono>b</Chip>);
    expect(plain.firstElementChild?.className).not.toContain('font-mono');
    expect(mono.firstElementChild?.className).toContain('font-mono');
  });
});

describe('Field', () => {
  it('renders the label and the wrapped control', () => {
    render(
      <Field label="Seed">
        <input aria-label="seed input" />
      </Field>,
    );
    expect(screen.getByText('Seed')).toBeTruthy();
    expect(screen.getByLabelText('seed input')).toBeTruthy();
  });

  it('associates the label with the control through htmlFor', () => {
    render(
      <Field label="Seed" htmlFor="seed">
        <input id="seed" />
      </Field>,
    );
    expect(screen.getByLabelText('Seed')).toBeTruthy();
  });

  it('renders a hint only when one is supplied', () => {
    const { rerender } = render(
      <Field label="Seed">
        <input />
      </Field>,
    );
    expect(screen.queryByText('Any integer')).toBeNull();
    rerender(
      <Field label="Seed" hint="Any integer">
        <input />
      </Field>,
    );
    expect(screen.getByText('Any integer')).toBeTruthy();
  });

  it('swaps the input border to the failed token in the error state', () => {
    expect(inputCls(false)).toContain('border-border-strong');
    expect(inputCls(true)).toContain('--s-failed-border');
    expect(inputCls(true)).not.toContain('border-border-strong');
  });
});

describe('SectionHeader', () => {
  it('renders the title as a heading', () => {
    render(<SectionHeader title="Prototypes" />);
    expect(screen.getByRole('heading', { name: 'Prototypes' })).toBeTruthy();
  });

  it('keeps the uppercase treatment while accepting extra classes', () => {
    const { container } = render(<SectionHeader title="A" className="mt-4" />);
    const cls = container.firstElementChild?.className ?? '';
    expect(cls).toContain('uppercase');
    expect(cls).toContain('mt-4');
  });
});
