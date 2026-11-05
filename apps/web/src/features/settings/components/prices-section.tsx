"use client";

import { CircleDollarSignIcon, PlusIcon, Trash2Icon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import { formatUsd } from "@/lib/format";

import { useDeletePrice, usePrices, useSavePrice } from "../api";

import { Card } from "./shared";

export function PricesSection() {
  const prices = usePrices();
  const save = useSavePrice();
  const remove = useDeletePrice();
  const [form, setForm] = React.useState({ provider: "openai", model: "", input: "", output: "" });

  return (
    <div className="space-y-5">
      <Card title="Price per million tokens" description="Every cost in SupportDesk is tokens times these prices. Defaults ship for common models; add or override yours. Local models cost 0.">
        {prices.isLoading ? (
          <TableSkeleton rows={4} cols={4} />
        ) : prices.isError ? (
          <ErrorState compact error={prices.error} onRetry={() => void prices.refetch()} />
        ) : !prices.data?.length ? (
          <EmptyState compact icon={CircleDollarSignIcon} title="No prices" description="Without a price, calls are recorded with a cost of 0. Add the models you use below." />
        ) : (
          <div className="-mx-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Model</TableHead>
                  <TableHead className="text-right">Input</TableHead>
                  <TableHead className="text-right">Output</TableHead>
                  <TableHead className="w-24 text-right"><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {prices.data.map((p) => (
                  <TableRow key={`${p.provider}/${p.model}`}>
                    <TableCell>
                      <span className="font-medium">{p.model}</span> <span className="text-muted-foreground">{p.provider}</span>
                    </TableCell>
                    <TableCell className="text-right tabular">{formatUsd(p.input_per_mtok)}</TableCell>
                    <TableCell className="text-right tabular">{formatUsd(p.output_per_mtok)}</TableCell>
                    <TableCell className="text-right">
                      {p.default || !p.id ? (
                        <Chip tone="neutral">Default</Chip>
                      ) : (
                        <Button size="icon-xs" variant="subtle" aria-label={`Remove price of ${p.model}`} disabled={remove.isPending} onClick={() => p.id && remove.mutate(p.id, { onSuccess: () => toast.success("Price removed."), onError: (e) => toast.error(errorMessage(e)) })}>
                          <Trash2Icon />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
      <Card title="Add or override a price" description="Same provider and model replaces the existing price. Applies to calls from now on.">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_1.4fr_1fr_1fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(
              { provider: form.provider.trim(), model: form.model.trim(), input_per_mtok: form.input || "0", output_per_mtok: form.output || "0" },
              { onSuccess: () => { toast.success("Price saved."); setForm({ ...form, model: "", input: "", output: "" }); }, onError: (err) => toast.error(errorMessage(err)) },
            );
          }}
        >
          <label className="space-y-1 text-[12px] text-muted-foreground">Provider<Input value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} required /></label>
          <label className="space-y-1 text-[12px] text-muted-foreground">Model<Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} required placeholder="gpt-4o-mini" /></label>
          <label className="space-y-1 text-[12px] text-muted-foreground">Input $/M<Input type="number" min={0} step="0.001" value={form.input} onChange={(e) => setForm({ ...form, input: e.target.value })} placeholder="0.15" /></label>
          <label className="space-y-1 text-[12px] text-muted-foreground">Output $/M<Input type="number" min={0} step="0.001" value={form.output} onChange={(e) => setForm({ ...form, output: e.target.value })} placeholder="0.60" /></label>
          <Button type="submit" disabled={save.isPending || !form.model.trim()}><PlusIcon /> Save</Button>
        </form>
      </Card>
    </div>
  );
}
