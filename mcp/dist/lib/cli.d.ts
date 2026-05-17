export interface IxResult {
    ok: boolean;
    stdout: string;
    stderr: string;
    durationMs: number;
}
export declare function stripHeader(raw: string): string;
export declare function runIx(args: string[], opts?: {
    timeout?: number;
}): Promise<IxResult>;
//# sourceMappingURL=cli.d.ts.map