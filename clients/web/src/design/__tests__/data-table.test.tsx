import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { DataTable } from "../table/DataTable";

interface Row {
  id: string;
  name: string;
  domain: string;
  [k: string]: unknown;
}

describe("DataTable cell id format", () => {
  it("emits cell ids as `${row.id}:${header.key}` so split(':').pop() yields the header key", () => {
    const rows: Row[] = [
      { id: "row-1", name: "Alpha", domain: "example.com" },
      { id: "row-2", name: "Beta", domain: "example.org" },
    ];
    const headers = [
      { key: "name", header: "Name" },
      { key: "domain", header: "Domain" },
    ];

    const captured: { id: string; headerKey: string | undefined; value: unknown }[] = [];
    render(
      <DataTable rows={rows} headers={headers}>
        {({ rows: r }) => {
          for (const row of r) {
            for (const cell of row.cells) {
              captured.push({
                id: cell.id,
                headerKey: cell.id.split(":").pop(),
                value: cell.value,
              });
            }
          }
          return <div data-testid="render-prop" />;
        }}
      </DataTable>,
    );

    expect(captured).toEqual([
      { id: "row-1:name", headerKey: "name", value: "Alpha" },
      { id: "row-1:domain", headerKey: "domain", value: "example.com" },
      { id: "row-2:name", headerKey: "name", value: "Beta" },
      { id: "row-2:domain", headerKey: "domain", value: "example.org" },
    ]);
  });

  it("provides stable info.header values for each cell", () => {
    const rows: Row[] = [{ id: "r1", name: "n", domain: "d" }];
    const headers = [
      { key: "name", header: "Name" },
      { key: "domain", header: "Domain" },
    ];
    const seen: string[] = [];
    render(
      <DataTable rows={rows} headers={headers}>
        {({ rows: r }) => {
          for (const cell of r[0].cells) seen.push(cell.info.header);
          return <div />;
        }}
      </DataTable>,
    );
    expect(seen).toEqual(["name", "domain"]);
  });
});
