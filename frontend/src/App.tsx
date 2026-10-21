import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { api } from "./api";
import {
  active,
  cellValue,
  countRows,
  filterRows,
  issueCell,
  labelStatus,
  recordsFor,
} from "./format";
import { JoinReceipt } from "./JoinReceipt";
import type {
  Cell,
  ChallengeReport,
  Job,
  PreviewReport,
  ReviewQueue,
  ReviewQueueItem,
  Result,
  Sample,
  SourceRecord,
} from "./types";

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    upload: (
      <>
        <path d="M12 16V3m-5 5 5-5 5 5" />
        <path d="M4 15v5h16v-5" />
      </>
    ),
    arrow: (
      <>
        <path d="M4 12h16m-6-6 6 6-6 6" />
      </>
    ),
    file: (
      <>
        <path d="M14 3H5v18h14V8l-5-5Z" />
        <path d="M14 3v5h5M8 12h8m-8 4h6" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    shield: (
      <>
        <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 10h18M3 15h18M9 4v16M15 4v16" />
      </>
    ),
    eye: (
      <>
        <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    download: (
      <>
        <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
      </>
    ),
    close: <path d="m6 6 12 12M6 18 18 6" />,
    chevron: <path d="m9 5 7 7-7 7" />,
    left: <path d="m15 5-7 7 7 7" />,
    history: (
      <>
        <path d="M3 10a9 9 0 1 1 1 7M3 4v6h6" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    plus: <path d="M12 4v16M4 12h16" />,
    warning: (
      <>
        <path d="m12 3 10 18H2L12 3Z" />
        <path d="M12 9v5m0 3v.1" />
      </>
    ),
    link: (
      <>
        <path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 12a4 4 0 0 0 6 0l5-5a4 4 0 0 0-6-6l-1 1" />
      </>
    ),
    lock: (
      <>
        <rect x="5" y="10" width="14" height="11" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </>
    ),
    spark: (
      <>
        <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" />
      </>
    ),
    trash: (
      <>
        <path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7" />
        <path d="M10 11v6m4-6v6" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.file}
    </svg>
  );
}
function Logo() {
  return (
    <span className="brand">
      <span className="brand-mark">
        <Icon name="grid" size={23} />
        <span>✓</span>
      </span>
      <span className="brand-name">Truecell</span>
      <span className="brand-studio">DOCUMENT INTELLIGENCE</span>
    </span>
  );
}
function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something interrupted the request. Please try again.";
}
function Modal({
  title,
  children,
  onClose,
  dismissible = true,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  dismissible?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="modal"
      aria-labelledby={id}
      onCancel={(event) => {
        event.preventDefault();
        if (dismissible) onClose();
      }}
      onClick={(e) => {
        if (dismissible && e.target === dialog.current) onClose();
      }}
      aria-busy={!dismissible}
    >
      <div className="modal-top">
        <h2 id={id}>{title}</h2>
        <button
          className="icon-button"
          onClick={onClose}
          disabled={!dismissible}
          aria-label="Close dialog"
        >
          <Icon name="close" />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export default function App() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState(false);
  const [about, setAbout] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Job | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [pollKey, setPollKey] = useState(0);
  const pollError = useRef("");
  useEffect(() => {
    let disposed = false;
    const health = () =>
      api
        .health()
        .then(() => {
          if (!disposed) setOnline(true);
        })
        .catch(() => {
          if (!disposed) setOnline(false);
        });
    void health();
    const timer = setInterval(() => void health(), 15000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    if (!online) return;
    let disposed = false;
    api
      .samples()
      .then((response) => {
        if (!disposed) setSamples(response.samples);
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, [online]);
  useEffect(() => {
    if (!job?.id) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const current = await api.job(job.id, controller.signal);
        if (disposed) return;
        if (pollError.current) {
          const recovered = pollError.current;
          setError((currentError) =>
            currentError === recovered ? "" : currentError,
          );
          pollError.current = "";
        }
        setJob(current);
        setOnline(true);
        if (active(current.status)) timer = setTimeout(() => void poll(), 1000);
      } catch (e) {
        if (!disposed) {
          const detail = message(e);
          pollError.current = detail;
          setError(detail);
          timer = setTimeout(() => void poll(), 3500);
        }
      }
    };
    void poll();
    return () => {
      disposed = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [job?.id, pollKey]);
  const start = async (operation: () => Promise<Job>) => {
    setBusy(true);
    setError("");
    try {
      setJob(await operation());
      setOnline(true);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  const openHistory = async () => {
    setHistory(true);
    setDeleteTarget(null);
    setDeleteError("");
    setError("");
    try {
      setJobs((await api.jobs()).jobs);
    } catch (e) {
      setError(message(e));
    }
  };
  const openJob = async (id: string) => {
    setBusy(true);
    setError("");
    try {
      setJob(await api.job(id));
      setHistory(false);
      setPollKey((k) => k + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  const removeWorkspace = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await api.remove(deleteTarget.id, deleteTarget.name);
      setJobs((current) => current.filter((item) => item.id !== deleteTarget.id));
      setJob((current) => (current?.id === deleteTarget.id ? null : current));
      setDeleteTarget(null);
    } catch (e) {
      setDeleteError(message(e));
    } finally {
      setDeleting(false);
    }
  };
  return (
    <>
      <header className="topbar">
        <button
          className="brand-button"
          onClick={() => setJob(null)}
          aria-label="Truecell home"
        >
          <Logo />
        </button>
        <nav aria-label="Main navigation">
          <button className="nav-button" onClick={() => void openHistory()}>
            <Icon name="history" size={17} /> Saved workspaces
          </button>
          <button className="nav-button" onClick={() => setAbout(true)}>
            How it works
          </button>
        </nav>
        <span
          className={`engine-status ${online === false ? "unavailable" : ""}`}
          aria-label={
            online === null
              ? "Connecting to local engine"
              : online
                ? "Local engine connected"
                : "Local engine unavailable"
          }
        >
          <i />
          <span className="engine-label">
            {online === null
              ? "Connecting"
              : online
                ? "Local engine connected"
                : "Engine unavailable"}
          </span>
          <span className="engine-label-short" aria-hidden="true">
            {online === null ? "Wait" : online ? "Online" : "Offline"}
          </span>
        </span>
      </header>
      {error && (
        <div className="global-error" role="alert">
          <Icon name="warning" />
          <span>{error}</span>
          <button
            className="icon-button"
            onClick={() => setError("")}
            aria-label="Dismiss error"
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      )}
      {job ? (
        <Workspace
          key={job.id}
          job={job}
          onJob={setJob}
          onError={setError}
          onNew={() => setJob(null)}
          onRefresh={() => setPollKey((k) => k + 1)}
        />
      ) : (
        <Landing
          samples={samples}
          busy={busy}
          onUpload={(f, v, o, languages) =>
            void start(() => api.upload(f, v, o, languages))
          }
          onSample={(f) => void start(() => api.sample(f))}
        />
      )}
      <footer className="site-footer">
        <span>
          <Icon name="lock" size={13} /> Local processing. Your source stays on
          this computer.
        </span>
        <span>Truecell · Document intelligence with a paper trail.</span>
      </footer>
      {history && (
        <Modal title="Saved workspaces" onClose={() => setHistory(false)}>
          <p className="muted">
            Pick up where you left off. Original readings and review history
            stay together.
          </p>
          <div className="job-list">
            {jobs.length ? (
              jobs.map((j) => (
                <div className="job-row" key={j.id}>
                  <button
                    className="job-open"
                    disabled={busy || deleting}
                    onClick={() => void openJob(j.id)}
                  >
                    <span className="file-mini">
                      <Icon name="file" />
                    </span>
                    <span className="job-summary">
                      <strong>{j.name}</strong>
                      <small>
                        {j.created
                          ? new Date(j.created).toLocaleString()
                          : j.id.slice(0, 12)}
                      </small>
                    </span>
                    <span
                      className={`status-pill ${
                        j.status === "failed" || j.quality?.status === "needs_rescan"
                          ? "warning"
                          : ""
                      }`}
                    >
                      {j.quality?.status === "needs_rescan"
                        ? "Needs better scan"
                        : j.quality?.status === "needs_review"
                          ? "Review required"
                          : j.quality?.status === "reviewed"
                            ? "Reviewed"
                            : labelStatus(j.status)}
                    </span>
                    <Icon name="chevron" size={16} />
                  </button>
                  <button
                    className="job-delete"
                    disabled={busy || deleting || active(j.status)}
                    onClick={() => {
                      setDeleteError("");
                      setDeleteTarget(j);
                    }}
                    aria-label={`Delete workspace ${j.name}`}
                    title={
                      active(j.status)
                        ? "Wait for extraction to finish before deleting"
                        : `Delete ${j.name}`
                    }
                  >
                    <Icon name="trash" size={18} />
                  </button>
                </div>
              ))
            ) : (
              <p className="empty-note">
                No saved documents yet. Your first extraction will appear here.
              </p>
            )}
          </div>
        </Modal>
      )}
      {deleteTarget && (
        <Modal
          title="Delete this workspace?"
          dismissible={!deleting}
          onClose={() => {
            setDeleteTarget(null);
          }}
        >
          <div className="delete-confirmation">
            <span className="delete-confirmation-icon">
              <Icon name="trash" size={22} />
            </span>
            <div>
              <strong>{deleteTarget.name}</strong>
              <p>
                This permanently removes the saved source, extraction,
                corrections and audit history from this computer. This cannot
                be undone.
              </p>
            </div>
          </div>
          {deleteError && (
            <p className="field-error" role="alert">
              {deleteError}
            </p>
          )}
          <div className="delete-actions">
            <button
              className="secondary-button"
              disabled={deleting}
              onClick={() => setDeleteTarget(null)}
            >
              Cancel
            </button>
            <button
              className="danger-button"
              disabled={deleting}
              onClick={() => void removeWorkspace()}
            >
              {deleting ? <Spinner /> : <Icon name="trash" size={17} />}
              {deleting ? "Deleting…" : "Delete workspace"}
            </button>
          </div>
        </Modal>
      )}
      {about && (
        <Modal title="Every value has a trail." onClose={() => setAbout(false)}>
          <div className="about-steps">
            <article>
              <span>01</span>
              <h3>Read the document</h3>
              <p>
                Native PDF extraction and local OCR reconstruct tables,
                including scans and page continuations.
              </p>
            </article>
            <article>
              <span>02</span>
              <h3>Check the evidence</h3>
              <p>
                Inspect source boxes, original readings, competing extraction
                attempts and arithmetic relationships.
              </p>
            </article>
            <article>
              <span>03</span>
              <h3>Review and export</h3>
              <p>
                Corrections require a reason, refresh validation and preserve
                the original extraction. Excel includes the audit trail.
              </p>
            </article>
          </div>
          <p className="disclosure">
            Recognition scores and agreeing equations are evidence for review.
            They are not independently measured accuracy or a guarantee that a
            source value is correct.
          </p>
        </Modal>
      )}
    </>
  );
}

function Landing({
  samples,
  busy,
  onUpload,
  onSample,
}: {
  samples: Sample[];
  busy: boolean;
  onUpload: (
    file: File,
    verify: boolean,
    force: boolean,
    ocrLanguages: string,
  ) => void;
  onSample: (file: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [verify, setVerify] = useState(false);
  const [force, setForce] = useState(false);
  const [ocrLanguages, setOcrLanguages] = useState("eng");
  const [drag, setDrag] = useState(false);
  const [fileError, setFileError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const pick = (candidate?: File) => {
    if (!candidate) return;
    if (!/\.(pdf|png|jpe?g|tiff?|bmp|webp)$/i.test(candidate.name)) {
      setFileError("Choose a PDF, PNG, JPEG, TIFF, BMP or WebP document.");
      return;
    }
    if (candidate.size > 50 * 1024 * 1024) {
      setFileError(
        "This document exceeds the 50 MB upload limit. Use a smaller copy.",
      );
      return;
    }
    if (!candidate.size) {
      setFileError("The selected file is empty. Choose another document.");
      return;
    }
    setFile(candidate);
    setFileError("");
  };
  const preferred = [
    "A_invoice_register.pdf",
    "B_bank_errors.pdf",
    "D_skew_5deg.pdf",
  ];
  const quick = preferred
    .map((name) => samples.find((s) => s.filename === name))
    .filter((s): s is Sample => !!s);
  return (
    <main className="landing">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">
            <span /> FROM DOCUMENT TO DECISION
          </p>
          <h1>
            Every cell.
            <br />
            <span>Accounted for.</span>
          </h1>
          <p className="hero-description">
            Turn difficult documents into clean Excel.
            <br />
            Then see exactly where every value came from.
          </p>
          <div className="proof-chips">
            <span>
              <Icon name="file" size={15} /> Up to 200 pages
            </span>
            <span>
              <Icon name="lock" size={15} /> Offline OCR
            </span>
            <span>
              <Icon name="eye" size={15} /> Source evidence
            </span>
          </div>
          <div className="hero-note">
            <span className="note-line" />
            <p>
              <span>BUILT FOR TRUST</span>
              <br />
              <strong>
                “When a number doesn’t add up, Truecell shows you why.”
              </strong>
            </p>
          </div>
        </div>
        <section className="upload-card" aria-labelledby="upload-heading">
          <div className="card-eyebrow">
            <span>YOUR NEXT SPREADSHEET STARTS HERE</span>
            <span className="tiny-tag">LOCAL FIRST</span>
          </div>
          <h2 id="upload-heading">Bring the document.</h2>
          <p>We’ll find the tables and check the numbers.</p>
          <input
            ref={input}
            className="visually-hidden"
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
            aria-label="Select document"
            disabled={busy}
            onChange={(e) => pick(e.target.files?.[0])}
          />
          <button
            className={`dropzone ${drag ? "dragging" : ""} ${file ? "has-file" : ""}`}
            disabled={busy}
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              pick(e.dataTransfer.files[0]);
            }}
          >
            <span className="upload-symbol">
              <Icon name={file ? "file" : "upload"} size={29} />
            </span>
            <strong>{file ? file.name : "Drop your document here"}</strong>
            <span>
              {file
                ? `${(file.size / 1024 / 1024).toFixed(2)} MB · click to replace`
                : "or click to browse your files"}
            </span>
            <small>PDF · images · scanned documents · max 50 MB</small>
          </button>
          {fileError && (
            <p className="field-error" role="alert">
              {fileError}
            </p>
          )}
          <details className="extraction-options">
            <summary>
              Extraction options <span>Optional</span>
            </summary>
            <label>
              <input
                type="checkbox"
                checked={verify}
                onChange={(e) => setVerify(e.target.checked)}
              />{" "}
              Independently cross-check native pages with OCR{" "}
              <small>Takes longer; retains reading disagreements.</small>
            </label>
            <label>
              <input
                type="checkbox"
                checked={force}
                onChange={(e) => setForce(e.target.checked)}
              />{" "}
              Force OCR on every page{" "}
              <small>Use for a damaged or unreliable PDF text layer.</small>
            </label>
            <label className="language-option">
              <span>OCR language codes</span>
              <input
                type="text"
                value={ocrLanguages}
                list="ocr-language-presets"
                spellCheck={false}
                autoCapitalize="none"
                autoComplete="off"
                placeholder="eng or eng+tel"
                onChange={(event) => setOcrLanguages(event.target.value)}
              />
              <datalist id="ocr-language-presets">
                <option value="eng">English</option>
                <option value="eng+hin">English + Hindi</option>
                <option value="eng+tel">English + Telugu</option>
                <option value="eng+hin+tel">English + Hindi + Telugu</option>
              </datalist>
              <small>
                Use local Tesseract codes. Missing installed packs appear as
                review findings.
              </small>
            </label>
          </details>
          <button
            className="primary-button extract-button"
            disabled={!file || busy}
            onClick={() =>
              file && onUpload(file, verify, force, ocrLanguages.trim() || "eng")
            }
          >
            {busy ? <Spinner /> : <Icon name="spark" />}
            {busy ? "Opening workspace…" : "Extract & validate"}
            {!busy && <Icon name="arrow" size={19} />}
          </button>
          <p className="upload-privacy">
            <Icon name="shield" size={14} /> No API key. No document upload to a
            cloud AI.
          </p>
        </section>
      </section>
      <section className="demo-strip" aria-labelledby="demo-heading">
        <div>
          <p className="eyebrow">TRY A REAL DOCUMENT</p>
          <h2 id="demo-heading">See Truecell in action.</h2>
          <p>Choose a public sample. Extract, validate and trace every cell.</p>
        </div>
        <div className="demo-buttons">
          {quick.length ? (
            quick.map((sample, i) => (
              <button
                key={sample.filename}
                onClick={() => onSample(sample.filename)}
                disabled={busy}
              >
                <span className={`demo-icon demo-${i}`}>
                  <Icon
                    name={i === 0 ? "grid" : i === 1 ? "warning" : "file"}
                    size={22}
                  />
                </span>
                <span>
                  <strong>
                    {
                      [
                        "Invoice register",
                        "Find a wrong balance",
                        "Recover a skewed scan",
                      ][i]
                    }
                  </strong>
                  <small>
                    {
                      [
                        "Wide tables, across pages",
                        "Two equations. One discrepancy.",
                        "Local OCR with recovery",
                      ][i]
                    }
                  </small>
                </span>
                <Icon name="arrow" size={17} />
              </button>
            ))
          ) : (
            <p className="empty-note">
              Quick demos appear when the local engine connects.
            </p>
          )}
        </div>
      </section>
      <section className="value-strip">
        <article>
          <span>01 / EXTRACT</span>
          <h3>Structure complex documents.</h3>
          <p>
            Wide tables, wrapped cells and multi-page continuations become a
            clean, usable grid.
          </p>
        </article>
        <article>
          <span>02 / VERIFY</span>
          <h3>Check the numbers automatically.</h3>
          <p>
            Arithmetic checks flag suspicious totals, balances and empty or
            shifted columns.
          </p>
        </article>
        <article>
          <span>03 / TRACE</span>
          <h3>Inspect every exported cell.</h3>
          <p>
            Jump from a spreadsheet cell to its original page, reading and
            correction history.
          </p>
        </article>
      </section>
    </main>
  );
}

function Workspace({
  job,
  onJob,
  onError,
  onNew,
  onRefresh,
}: {
  job: Job;
  onJob: (job: Job) => void;
  onError: (error: string) => void;
  onNew: () => void;
  onRefresh: () => void;
}) {
  const result = job.result;
  const processing = active(job.status);
  const [tableIndex, setTableIndex] = useState(0);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Cell | null>(null);
  const [rail, setRail] = useState<
    "review" | "equations" | "challenge" | "audit"
  >("review");
  const [review, setReview] = useState(false);
  const [gridPage, setGridPage] = useState(0);
  const [tableSearch, setTableSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueView, setQueueView] = useState<ReviewQueue | null>(null);
  const [showEvidence, setShowEvidence] = useState(true);
  const table = result?.tables[tableIndex];
  const reviewed =
    result?.review.status === "reviewed" &&
    result.review.fingerprint === job.fingerprint;
  const protectedCopy =
    !!result &&
    (result.history.length > 0 || result.review.status === "reviewed");
  const columnCount =
    table?.rows.reduce(
      (width, row) => Math.max(width, row.length),
      table.headers.length,
    ) ?? 0;
  const filteredRows = useMemo(
    () => (table ? filterRows(table.headers, table.rows, tableSearch) : []),
    [table, tableSearch],
  );
  const maxGridPage = Math.max(0, Math.ceil(filteredRows.length / 40) - 1);
  const visibleGridPage = Math.min(gridPage, maxGridPage);
  const visibleRows = filteredRows.slice(
    visibleGridPage * 40,
    (visibleGridPage + 1) * 40,
  );

  useEffect(() => {
    setGridPage(0);
  }, [result]);

  useEffect(() => {
    setGridPage((current) => Math.min(current, maxGridPage));
  }, [maxGridPage]);

  const select = (cell: Cell) => {
    setTableIndex(cell.table);
    setSelected(cell);
    setShowEvidence(true);
    if (cell.row >= 0) {
      const filteredIndex =
        cell.table === tableIndex
          ? filteredRows.findIndex((entry) => entry.rowIndex === cell.row)
          : -1;
      if (filteredIndex >= 0) {
        setGridPage(Math.floor(filteredIndex / 40));
      } else {
        setTableSearch("");
        setGridPage(Math.floor(cell.row / 40));
      }
    }
    const sources = result ? recordsFor(result, cell) : [];
    if (sources.length) setPage(sources[0].page);
  };
  const records = result && selected ? recordsFor(result, selected) : [];
  const emptyReviewQueue: ReviewQueue = {
    items: [],
    total: 0,
    visible: 0,
    pending: 0,
    checked: 0,
    filtered_total: 0,
    filtered_pending: 0,
    offset: 0,
    limit: 100,
    remaining: 0,
    has_more: false,
    next_offset: null,
    omitted: 0,
    confidence_threshold: 0.93,
  };
  const globalReviewQueue = job.review_queue ?? emptyReviewQueue;
  const reviewQueue = queueView ?? globalReviewQueue;
  useEffect(() => {
    if (!result) {
      setQueueView(null);
      return;
    }
    let current = true;
    setQueueLoading(true);
    api
      .reviewQueue(job.id, 0, 100, tableIndex)
      .then((queue) => {
        if (current) setQueueView(queue);
      })
      .catch((error) => {
        if (current) onError(message(error));
      })
      .finally(() => {
        if (current) setQueueLoading(false);
      });
    return () => {
      current = false;
    };
  }, [
    job.id,
    job.fingerprint,
    job.review_queue?.checked,
    job.review_queue?.pending,
    onError,
    result,
    tableIndex,
  ]);
  const loadMoreReviewItems = async () => {
    if (queueLoading || reviewQueue.next_offset == null) return;
    setQueueLoading(true);
    try {
      const next = await api.reviewQueue(
        job.id,
        reviewQueue.next_offset,
        100,
        tableIndex,
      );
      setQueueView((current) => {
        if (!current) return next;
        const items = [...current.items, ...next.items];
        return { ...next, items, visible: items.length, offset: 0 };
      });
    } catch (error) {
      onError(message(error));
    } finally {
      setQueueLoading(false);
    }
  };
  const relevantReviewItems = reviewQueue.items
    .filter((item) => item.table == null || item.table === tableIndex)
    .sort((a, b) => {
      if (a.status !== b.status) return a.status === "pending" ? -1 : 1;
      if (a.kind !== b.kind) return a.kind === "finding" ? -1 : 1;
      return (a.confidence ?? 1) - (b.confidence ?? 1);
    });
  const flagged = useMemo(
    () =>
      new Set(
        (result?.issues ?? [])
          .map((i) => (result ? issueCell(result, i) : null))
          .filter((c): c is Cell => c !== null)
          .map((c) => `${c.table}:${c.row}:${c.column}`),
      ),
    [result],
  );
  const mutate = async (operation: () => Promise<Job>) => {
    setSaving(true);
    onError("");
    try {
      onJob(await operation());
    } catch (e) {
      onError(message(e));
    } finally {
      setSaving(false);
    }
  };
  const chooseTable = (index: number) => {
    setTableIndex(index);
    setGridPage(0);
    setSelected(null);
    if (result?.tables[index]) setPage(result.tables[index].page);
  };
  return (
    <main className="workspace">
      <div className="workspace-heading">
        <div>
          <button className="back-link" onClick={onNew}>
            <Icon name="left" size={14} /> New document
          </button>
          <div className="document-heading">
            <span className="file-badge">
              <Icon name="file" size={24} />
            </span>
            <div>
              <h1>{job.name}</h1>
              <div className="document-meta">
                <span
                  className={`status-pill ${job.status === "failed" || job.status === "partial" ? "warning" : ""}`}
                >
                  {processing && <Spinner />}
                  {labelStatus(job.status)}
                </span>
                {result && (
                  <>
                    <span>{result.seconds.toFixed(1)}s</span>
                    <span className={reviewed ? "reviewed-label" : "muted"}>
                      {reviewed
                        ? "Source check recorded"
                        : "Awaiting source review"}
                    </span>
                    <span
                      className={
                        job.quality?.status === "needs_rescan"
                          ? "quality-label quality-rescan"
                          : job.quality?.status === "reviewed"
                            ? "quality-label quality-reviewed"
                            : "quality-label"
                      }
                      title={job.quality?.reasons.join(" ")}
                    >
                      {job.quality?.status === "needs_rescan"
                        ? "Needs better scan"
                        : job.quality?.status === "reviewed"
                          ? "Reviewed"
                          : "Review required"}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="export-actions">
          {result && (
            <>
              <a
                className="secondary-button"
                href={api.download(job.id, "audit.json")}
                download
              >
                <Icon name="download" size={16} /> Audit JSON
              </a>
              {job.quality?.draft_export_ready ? (
                <>
                  <a
                    className="secondary-button"
                    href={api.download(job.id, "export.xlsx")}
                    download
                  >
                    <Icon name="download" size={17} /> Draft Excel
                  </a>
                  <a
                    className="secondary-button"
                    href={api.csv(job.id, tableIndex)}
                    download
                  >
                    <Icon name="download" size={16} /> CSV
                  </a>
                </>
              ) : (
                <button
                  className="secondary-button"
                  disabled
                  title="No table data is available. Download the audit JSON and retry the source."
                >
                  <Icon name="warning" size={16} /> No table export
                </button>
              )}
              {job.quality?.reviewed_export_ready ? (
                <a
                  className="primary-button"
                  href={api.download(job.id, "reviewed.xlsx")}
                  download
                >
                  <Icon name="shield" size={17} /> Reviewed Excel
                </a>
              ) : (
                <button
                  className="primary-button"
                  disabled
                  title="Check every review item and record the final source attestation first."
                >
                  <Icon name="shield" size={17} /> Reviewed Excel
                </button>
              )}
            </>
          )}
        </div>
      </div>
      {job.forked_from && (
        <p className="previous-extraction-note">
          New extraction. The original reviewed workspace and its correction
          history are preserved.
        </p>
      )}
      {processing && (
        <section className="processing-card" aria-live="polite">
          <span className="processing-orbit">
            <Icon name="grid" size={29} />
          </span>
          <div>
            <p className="eyebrow">THE ENGINE IS AT WORK</p>
            <h2>
              {job.progress_pages
                ? `Reading page ${job.progress_page ?? 0} of ${job.progress_pages}`
                : "Inspecting your document…"}
            </h2>
            <p>
              Extracting structure, retaining evidence and checking the numbers.
              You can reopen this workspace later.
            </p>
            <progress
              max="1"
              value={Math.max(0, Math.min(1, job.progress ?? 0))}
            />
          </div>
          <span className="progress-percent">
            {Math.round((job.progress ?? 0) * 100)}%
          </span>
        </section>
      )}
      {(job.error || job.status === "failed" || job.status === "partial") && (
        <div className="workspace-warning" role="alert">
          <Icon name="warning" />
          <div>
            <strong>Processing needs attention.</strong>
            <p>
              {job.error ||
                "One or more pages did not finish. Verified completed page checkpoints can be reused."}
            </p>
            {(job.status === "failed" || job.status === "partial") && (
              <>
                <button
                  className="secondary-button resume-button"
                  disabled={saving || processing}
                  onClick={() =>
                    void mutate(async () => {
                      const resumed = await api.process(job.id, {
                        verify: job.options?.verify ?? false,
                        force_ocr:
                          job.options?.force_ocr ?? job.options?.force ?? false,
                        ocr_languages: job.options?.ocr_languages ?? "eng",
                      });
                      onRefresh();
                      return resumed;
                    })
                  }
                >
                  {saving ? <Spinner /> : <Icon name="history" size={15} />}{" "}
                  {protectedCopy
                    ? "Re-extract in a new workspace"
                    : "Resume verified checkpoints"}
                </button>
                {protectedCopy && (
                  <p className="disclosure">
                    A new extraction preserves your original reviewed workspace
                    and correction history.
                  </p>
                )}
              </>
            )}
            <button className="text-button" onClick={onRefresh}>
              Refresh workspace
            </button>
          </div>
        </div>
      )}
      {result && (
        <>
          {processing && (
            <p className="previous-extraction-note">
              The previous extraction is shown while recovery runs. Corrections
              and source checks are paused.
            </p>
          )}
          <section className="summary-bar" aria-label="Extraction summary">
            <div>
              <Icon name="file" />
              <strong>{result.pages.length}</strong>
              <span>pages</span>
            </div>
            <div>
              <Icon name="grid" />
              <strong>{result.tables.length}</strong>
              <span>tables</span>
            </div>
            <div>
              <strong>{countRows(result).toLocaleString()}</strong>
              <span>data rows</span>
            </div>
            <div className={globalReviewQueue.pending ? "summary-findings" : ""}>
              <Icon name={globalReviewQueue.pending ? "warning" : "check"} />
              <strong>{globalReviewQueue.pending}</strong>
              <span>items to review</span>
            </div>
            <button
              onClick={() => setReview(true)}
              className="review-button"
              disabled={processing || saving}
            >
              <Icon name="shield" size={17} />
              {reviewed ? "View source check" : "Record source check"}
              <Icon name="chevron" size={15} />
            </button>
          </section>
          <div className="workspace-flow">
            <span>
              <i>1</i> Original source
            </span>
            <Icon name="arrow" size={16} />
            <span>
              <i>2</i> Structured extraction
            </span>
            <Icon name="arrow" size={16} />
            <span>
              <i>3</i> Validation & evidence
            </span>
          </div>
          <section className="document-workspace">
            <SourcePane
              job={job}
              page={page}
              setPage={setPage}
              records={records}
            />
            <section className="grid-pane" aria-label="Extracted table">
              <div className="pane-heading">
                <div>
                  <Icon name="grid" size={17} />
                  <h2>Extracted data</h2>
                </div>
                {table && (
                  <select
                    aria-label="Select extracted table"
                    value={tableIndex}
                    onChange={(e) => chooseTable(Number(e.target.value))}
                  >
                    {result.tables.map((t, i) => (
                      <option key={i} value={i}>
                        Table {i + 1} · {t.rows.length} rows
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="grid-hint">
                <span>
                  <span className="selection-dot" />
                  Select any cell to follow its source.
                </span>
                {table && <small>{table.headers.length} columns</small>}
              </div>
              {table && <JoinReceipt table={table} />}
              {table ? (
                <>
                  <div className="table-search-bar">
                    <div className="table-search-field">
                      <Icon name="search" size={15} />
                      <input
                        type="search"
                        aria-label="Search extracted data"
                        value={tableSearch}
                        placeholder="Search this table"
                        autoComplete="off"
                        onChange={(event) => {
                          setTableSearch(event.target.value);
                          setGridPage(0);
                        }}
                      />
                      {tableSearch && (
                        <button
                          type="button"
                          className="table-search-clear"
                          aria-label="Clear table search"
                          onClick={() => {
                            setTableSearch("");
                            setGridPage(0);
                          }}
                        >
                          <Icon name="close" size={14} />
                        </button>
                      )}
                    </div>
                    <span className="table-search-count" role="status">
                      {tableSearch.trim()
                        ? `${filteredRows.length.toLocaleString()} of ${table.rows.length.toLocaleString()} rows`
                        : `${table.rows.length.toLocaleString()} rows`}
                    </span>
                  </div>
                  <div className="table-scroll">
                    <table className="data-grid">
                      <thead>
                        <tr>
                          <th className="row-number">#</th>
                          {Array.from(
                            { length: columnCount },
                            (_, c) => table.headers[c] ?? "Extra column",
                          ).map((h, c) => (
                            <th key={c}>
                              <button
                                disabled={c >= table.headers.length}
                                className={
                                  selected?.row === -1 && selected.column === c
                                    ? "selected-header"
                                    : ""
                                }
                                onClick={() =>
                                  select({
                                    table: tableIndex,
                                    row: -1,
                                    column: c,
                                  })
                                }
                                title={`Inspect header ${h}`}
                              >
                                {h || `Column ${c + 1}`}
                              </button>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {visibleRows.map(({ rowIndex: r, row }) => (
                          <tr key={r}>
                            <th className="row-number" scope="row">
                              {r + 1}
                            </th>
                            {Array.from(
                              {
                                length: Math.max(
                                  table.headers.length,
                                  row.length,
                                ),
                              },
                              (_, c) => {
                                const isSelected =
                                  selected?.table === tableIndex &&
                                  selected.row === r &&
                                  selected.column === c;
                                const isFlagged = flagged.has(
                                  `${tableIndex}:${r}:${c}`,
                                );
                                return (
                                  <td key={c}>
                                    <button
                                      disabled={c >= row.length}
                                      onClick={() =>
                                        select({
                                          table: tableIndex,
                                          row: r,
                                          column: c,
                                        })
                                      }
                                      className={`${isSelected ? "selected-cell " : ""}${isFlagged ? "flagged-cell" : ""}`}
                                      aria-label={`Row ${r + 1}, ${table.headers[c] ?? `column ${c + 1}`}: ${row[c] || "empty"}`}
                                      aria-pressed={isSelected}
                                    >
                                      {row[c] || (
                                        <span className="empty-cell">—</span>
                                      )}
                                      {isFlagged && (
                                        <i className="flag-indicator" />
                                      )}
                                    </button>
                                  </td>
                                );
                              },
                            )}
                          </tr>
                        ))}
                        {visibleRows.length === 0 && (
                          <tr className="table-no-results">
                            <td colSpan={columnCount + 1}>
                              <div>
                                <Icon name="search" size={19} />
                                <strong>No matching rows</strong>
                                <span>Try another word or clear the search.</span>
                              </div>
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  <div className="table-pagination">
                    <span>
                      {filteredRows.length ? visibleGridPage * 40 + 1 : 0}–
                      {Math.min(
                        (visibleGridPage + 1) * 40,
                        filteredRows.length,
                      )}{" "}
                      of {filteredRows.length.toLocaleString()}
                      {tableSearch.trim() ? " matches" : " rows"}
                    </span>
                    <div>
                      <button
                        className="icon-button"
                        aria-label="Previous table rows"
                        disabled={visibleGridPage === 0}
                        onClick={() => setGridPage((p) => p - 1)}
                      >
                        <Icon name="left" size={16} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label="Next table rows"
                        disabled={
                          (visibleGridPage + 1) * 40 >= filteredRows.length
                        }
                        onClick={() => setGridPage((p) => p + 1)}
                      >
                        <Icon name="chevron" size={16} />
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="grid-empty">
                  <Icon name="grid" size={38} />
                  <h3>No table reconstructed</h3>
                  <p>
                    Inspect the source and engine audit. Findings and audit
                    exports remain available.
                  </p>
                  <button
                    className="secondary-button"
                    onClick={() => setRail("audit")}
                  >
                    Inspect attempts
                  </button>
                </div>
              )}
            </section>
            <aside className="validation-pane">
              <div
                className="rail-tabs"
                role="tablist"
                aria-label="Review panels"
              >
                {(["review", "equations", "challenge", "audit"] as const).map(
                  (t) => (
                    <button
                      role="tab"
                      aria-selected={rail === t}
                      key={t}
                      onClick={() => setRail(t)}
                    >
                      {t === "review"
                        ? "Review"
                        : t === "equations"
                          ? "Equations"
                          : t === "challenge"
                            ? "Challenge"
                            : "Audit"}
                      {t === "review" && (
                        <span>
                          {
                            relevantReviewItems.filter(
                              (item) => item.status === "pending",
                            ).length
                          }
                        </span>
                      )}
                    </button>
                  ),
                )}
              </div>
              {rail === "review" && (
                <div className="rail-content">
                  <div className="queue-overview">
                    <p className="rail-intro">
                      Inspect priority cells against their original reading,
                      then mark each one checked.
                    </p>
                    <div aria-label="Review queue progress">
                      <strong>
                        {reviewQueue.filtered_total - reviewQueue.filtered_pending}/
                        {reviewQueue.filtered_total}
                      </strong>
                      <span>checked</span>
                      <progress
                        max={Math.max(1, reviewQueue.filtered_total)}
                        value={
                          reviewQueue.filtered_total - reviewQueue.filtered_pending
                        }
                      />
                    </div>
                  </div>
                  {relevantReviewItems.length ? (
                    relevantReviewItems.map((item) => (
                      <ReviewQueueCard
                        key={item.id}
                        item={item}
                        saving={saving}
                        onInspect={() => {
                          if (
                            item.table != null &&
                            item.row != null &&
                            item.column != null
                          ) {
                            select({
                              table: item.table,
                              row: item.row,
                              column: item.column,
                            });
                          } else {
                            setSelected(null);
                            setShowEvidence(false);
                            setPage(item.page);
                          }
                        }}
                        onReview={() =>
                          void mutate(() =>
                            api.reviewItem(
                              job.id,
                              item.id,
                              item.status !== "checked",
                              job.fingerprint,
                            ),
                          )
                        }
                      />
                    ))
                  ) : (
                    <div className="no-findings">
                      <span>
                        <Icon name="check" size={25} />
                      </span>
                      <h3>Priority queue is clear</h3>
                      <p>
                        No validation finding or low-confidence reading needs
                        attention in this table.
                      </p>
                    </div>
                  )}
                  {reviewQueue.has_more && (
                    <button
                      className="secondary-button queue-load-more"
                      disabled={queueLoading}
                      onClick={() => void loadMoreReviewItems()}
                    >
                      {queueLoading ? <Spinner /> : <Icon name="plus" size={14} />}
                      Load {Math.min(100, reviewQueue.remaining).toLocaleString()} more
                      <span>({reviewQueue.remaining.toLocaleString()} remaining)</span>
                    </button>
                  )}
                  <div className="rail-footnote">
                    <Icon name="eye" size={16} />
                    <p>
                      Queue items indicate uncertainty or a rule finding, not a
                      confirmed source error.
                    </p>
                  </div>
                </div>
              )}
              {rail === "equations" && (
                <div className="rail-content">
                  <p className="rail-intro">
                    Relationships discovered from repeating numeric patterns.
                  </p>
                  {result.constraints
                    .filter((r) => r.table === tableIndex + 1)
                    .map((r, i) => (
                      <article className="equation-card" key={i}>
                        <code>{r.formula}</code>
                        <p>
                          <strong>
                            {r.matched}/{r.checked}
                          </strong>{" "}
                          eligible rows agree
                        </p>
                        <span
                          className={
                            r.violations.length ? "text-amber" : "text-teal"
                          }
                        >
                          {r.violations.length} discrepancies
                        </span>
                      </article>
                    ))}
                  {!result.constraints.some(
                    (r) => r.table === tableIndex + 1,
                  ) && (
                    <p className="empty-note">
                      Not enough repeated numeric evidence to infer a
                      relationship.
                    </p>
                  )}
                  {result.proposals
                    .filter((p) => p.table === tableIndex + 1)
                    .map((p, i) => (
                      <button
                        key={i}
                        className="proposal-card"
                        onClick={() =>
                          select({
                            table: tableIndex,
                            row: p.row,
                            column: p.column,
                          })
                        }
                      >
                        <span>
                          <Icon name="spark" size={15} /> Review a proposal
                        </span>
                        <strong>
                          {p.observed} <Icon name="arrow" size={14} />{" "}
                          {p.proposed}
                        </strong>
                        <small>
                          {p.support_count} supporting equations · not applied
                        </small>
                      </button>
                    ))}
                  <p className="disclosure">
                    Agreeing equations can still be wrong. Suggestions never
                    change the original automatically.
                  </p>
                </div>
              )}
              {rail === "challenge" && (
                <ChallengePanel
                  key={`${job.id}:${job.fingerprint}:${tableIndex}`}
                  job={job}
                  tableIndex={tableIndex}
                  onCell={select}
                />
              )}
              {rail === "audit" && (
                <div className="rail-content">
                  <p className="rail-intro">
                    Selected strategies, recovery attempts and page errors.
                  </p>
                  {result.pages.map((p) => (
                    <article className="audit-page" key={p.page}>
                      <h3>
                        Page {p.page}
                        <span>{p.route}</span>
                      </h3>
                      {p.error && <p className="field-error">{p.error}</p>}
                      {p.attempts.map((a, i) => (
                        <div
                          key={i}
                          className={`attempt ${a.selected ? "chosen" : ""}`}
                        >
                          <span>
                            {a.selected ? (
                              <Icon name="check" size={13} />
                            ) : (
                              <i />
                            )}
                            {a.strategy}
                          </span>
                          <small>
                            {a.engine} · {a.seconds.toFixed(1)}s · {a.tables}{" "}
                            tables
                          </small>
                          {a.error && <p className="field-error">{a.error}</p>}
                        </div>
                      ))}
                    </article>
                  ))}
                  <a
                    href={api.download(job.id, "baseline.json")}
                    download
                    className="text-button"
                  >
                    Download original extraction{" "}
                    <Icon name="download" size={14} />
                  </a>
                  <details className="fingerprint">
                    <summary>Source SHA-256</summary>
                    <code>{result.source_sha256}</code>
                  </details>
                  <section
                    className="correction-history"
                    aria-labelledby="history-heading"
                  >
                    <h3 id="history-heading">
                      <Icon name="history" size={14} />
                      Correction history <span>{result.history.length}</span>
                    </h3>
                    {result.history.length ? (
                      <>
                        {result.history
                          .slice(-20)
                          .reverse()
                          .map((event, i) => (
                            <article key={String(event.sha256 ?? i)}>
                              <div>
                                <strong>
                                  Table {Number(event.table) + 1} ·{" "}
                                  {Number(event.row) < 0
                                    ? "header"
                                    : `row ${Number(event.row) + 1}`}{" "}
                                  · C{Number(event.column) + 1}
                                </strong>
                                <time>
                                  {typeof event.at === "string"
                                    ? new Date(event.at).toLocaleString()
                                    : ""}
                                </time>
                              </div>
                              <p>
                                <code>{String(event.before ?? "(empty)")}</code>
                                <Icon name="arrow" size={12} />
                                <code>{String(event.after ?? "(empty)")}</code>
                              </p>
                              <small>{String(event.note ?? "")}</small>
                            </article>
                          ))}
                        <p className="disclosure">
                          {result.history.length > 20
                            ? "Latest 20 changes shown. "
                            : ""}
                          Full history is included in the audit JSON. Hashes
                          detect changes; they do not establish reviewer
                          identity.
                        </p>
                      </>
                    ) : (
                      <p className="empty-note">
                        No corrections recorded. Original extraction values are
                        retained.
                      </p>
                    )}
                  </section>
                </div>
              )}
            </aside>
          </section>
          {selected && showEvidence && (
            <Evidence
              key={`${job.id}:${job.fingerprint}:${selected.table}:${selected.row}:${selected.column}`}
              result={result}
              cell={selected}
              records={records}
              saving={saving || processing}
              close={() => setShowEvidence(false)}
              onPage={setPage}
              onPreview={(value) =>
                api.preview(job.id, selected, value, job.fingerprint)
              }
              onSave={(value, note) =>
                void mutate(() =>
                  api.edit(job.id, selected, value, note, job.fingerprint),
                )
              }
            />
          )}
          {review && (
            <ReviewModal
              key={`${job.id}:${job.fingerprint}`}
              result={result}
              saving={saving || processing}
              reviewed={!!reviewed}
              pendingItems={globalReviewQueue.pending}
              onClose={() => setReview(false)}
              onReview={(note) =>
                void mutate(() => api.review(job.id, note, job.fingerprint))
              }
            />
          )}
        </>
      )}
      {!result && !processing && (
        <section className="no-result">
          <Icon name="file" size={36} />
          <h2>No extraction is available yet.</h2>
          <p>
            The original workspace is retained. Refresh its status or choose
            another document.
          </p>
          <button className="secondary-button" onClick={onRefresh}>
            Refresh workspace
          </button>
        </section>
      )}
    </main>
  );
}

function ChallengePanel({
  job,
  tableIndex,
  onCell,
}: {
  job: Job;
  tableIndex: number;
  onCell: (cell: Cell) => void;
}) {
  const [report, setReport] = useState<ChallengeReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const run = async () => {
    setRunning(true);
    setReport(null);
    setError("");
    try {
      setReport(await api.challenge(job.id, tableIndex, job.fingerprint));
    } catch (error) {
      setError(message(error));
    } finally {
      setRunning(false);
    }
  };
  return (
    <section
      className="rail-content challenge-panel"
      aria-labelledby="challenge-heading"
    >
      <span className="challenge-symbol">
        <Icon name="spark" size={23} />
      </span>
      <h3 id="challenge-heading">Find the validator’s blind spots.</h3>
      <p className="rail-intro">
        Hide the headers, change sampled numbers in disposable copies, and see
        which mistakes the actual validator catches.
      </p>
      <button
        className="primary-button challenge-run"
        disabled={
          running || active(job.status) || !job.result?.tables[tableIndex]
        }
        onClick={() => void run()}
      >
        {running ? <Spinner /> : <Icon name="spark" size={15} />}
        {running
          ? "Running controlled tests…"
          : "Run controlled error injections"}
      </button>
      <p className="challenge-scope">
        <Icon name="lock" size={12} />
        Working values and review history stay unchanged.
      </p>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {report && (
        <div className="challenge-results" aria-live="polite">
          <div className="challenge-metric">
            <strong>
              {report.caught}
              <span>/ {report.tested}</span>
            </strong>
            <p>test edits raised a new finding</p>
          </div>
          <p className="challenge-coverage">
            Tested {report.rows_tested} of {report.rows_available} data rows ·
            up to {report.row_limit} rows per run
          </p>
          <div className="unmodeled-columns">
            <span>Columns without inferred equations</span>
            <strong>
              {report.unmodeled_columns.length
                ? report.unmodeled_columns.map((c) => `C${c}`).join(", ")
                : "None"}
            </strong>
          </div>
          {report.cases.length ? (
            <ol
              className="challenge-cases"
              aria-label="Controlled injection results"
            >
              {report.cases.map((test, i) => (
                <li key={i}>
                  <button
                    onClick={() =>
                      onCell({
                        table: tableIndex,
                        row: test.row - 1,
                        column: test.column - 1,
                      })
                    }
                    title="Inspect the unchanged original cell"
                  >
                    <div>
                      <span>
                        R{test.row} · C{test.column}
                      </span>
                      <strong className={test.caught ? "caught" : "missed"}>
                        {test.caught ? "Detected" : "Missed"}
                      </strong>
                    </div>
                    <p>
                      <code>{test.original}</code>
                      <Icon name="arrow" size={12} />
                      <code>{test.mutated}</code>
                    </p>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="empty-note">
              No eligible numeric cells were available for controlled edits.
            </p>
          )}
          <p className="disclosure">
            Selecting a test opens the unchanged original cell. Misses remain
            visible.
          </p>
        </div>
      )}
      <p className="challenge-disclaimer">
        <strong>Validator sensitivity, not OCR accuracy.</strong> This tests
        arithmetic checks on this extraction. It does not measure
        hidden-document accuracy or guarantee error detection.
      </p>
    </section>
  );
}

function SourcePane({
  job,
  page,
  setPage,
  records,
}: {
  job: Job;
  page: number;
  setPage: (page: number) => void;
  records: SourceRecord[];
}) {
  const [size, setSize] = useState<{ width: number; height: number } | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(100);
  const pageCount = job.result?.pages.length ?? 1;
  useEffect(() => {
    setLoaded(false);
    setFailed(false);
    setSize(null);
    const controller = new AbortController();
    api
      .pageInfo(job.id, page, controller.signal)
      .then(setSize)
      .catch(() => {});
    return () => controller.abort();
  }, [job.id, page]);
  const boxes = records.filter((r) => r.page === page && r.bbox?.length === 4);
  return (
    <section className="source-pane" aria-label="Original document">
      <div className="pane-heading">
        <div>
          <Icon name="file" size={17} />
          <h2>Original source</h2>
        </div>
        <a
          href={api.download(job.id, "source")}
          target="_blank"
          rel="noreferrer"
          className="text-button"
        >
          Open file <Icon name="arrow" size={13} />
        </a>
      </div>
      <div className="source-toolbar">
        <div>
          <button
            className="icon-button"
            aria-label="Previous source page"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <Icon name="left" size={15} />
          </button>
          <label>
            <span className="visually-hidden">Source page</span>
            <select
              value={page}
              onChange={(e) => setPage(Number(e.target.value))}
            >
              {Array.from({ length: pageCount }, (_, i) => (
                <option key={i} value={i + 1}>
                  {i + 1}
                </option>
              ))}
            </select>
          </label>
          <span>/ {pageCount}</span>
          <button
            className="icon-button"
            aria-label="Next source page"
            disabled={page >= pageCount}
            onClick={() => setPage(page + 1)}
          >
            <Icon name="chevron" size={15} />
          </button>
        </div>
        <select
          aria-label="Source zoom"
          value={zoom}
          onChange={(e) => setZoom(Number(e.target.value))}
        >
          <option value={100}>Fit width</option>
          <option value={130}>130%</option>
          <option value={170}>170%</option>
        </select>
      </div>
      <div className="source-scroll">
        {failed ? (
          <div className="source-unavailable">
            <Icon name="warning" size={28} />
            <h3>Source preview unavailable</h3>
            <p>The extracted values and exports remain available.</p>
            <a
              href={api.download(job.id, "source")}
              className="text-button"
              target="_blank"
              rel="noreferrer"
            >
              Open original file
            </a>
          </div>
        ) : (
          <>
            <div className="source-sheet" style={{ width: `${zoom}%` }}>
              <img
                key={`${job.id}:${page}`}
                src={api.image(job.id, page)}
                alt={`Original source page ${page}`}
                onLoad={() => setLoaded(true)}
                onError={() => setFailed(true)}
              />
              {loaded && size && (
                <svg
                  className="source-overlay"
                  viewBox={`0 0 ${size.width} ${size.height}`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  {boxes.map((r, i) => {
                    const b = r.bbox!;
                    return (
                      <rect
                        key={i}
                        x={b[0]}
                        y={b[1]}
                        width={Math.max(1, b[2] - b[0])}
                        height={Math.max(1, b[3] - b[1])}
                        rx="1"
                      />
                    );
                  })}
                </svg>
              )}
            </div>
            {!loaded && (
              <span className="source-loading">
                <Spinner /> Loading source page…
              </span>
            )}
          </>
        )}
      </div>
      <div className="source-caption">
        <span className="source-outline-key" />
        {boxes.length && size
          ? "Selected cell outlined on source"
          : "Select a cell to locate its reading"}
      </div>
    </section>
  );
}

function ReviewQueueCard({
  item,
  saving,
  onInspect,
  onReview,
}: {
  item: ReviewQueueItem;
  saving: boolean;
  onInspect: () => void;
  onReview: () => void;
}) {
  const checked = item.status === "checked";
  return (
    <article className={`queue-card ${checked ? "queue-checked" : ""}`}>
      <div>
        <span className="queue-kind">
          <Icon
            name={
              checked ? "check" : item.kind === "finding" ? "warning" : "eye"
            }
            size={13}
          />
          {checked
            ? "Source checked"
            : item.kind === "finding"
              ? "Validation finding"
              : item.kind === "evidence"
                ? "Source location"
              : "Uncertain reading"}
        </span>
        <small>
          Page {item.page}
          {item.row != null ? ` · row ${item.row + 1}` : ""}
        </small>
      </div>
      <h3>{item.title}</h3>
      <p>{item.reason}</p>
      <div className="queue-actions">
        <button className="text-button" onClick={onInspect}>
          Inspect source <Icon name="arrow" size={13} />
        </button>
        <button
          className={checked ? "queue-reopen" : "queue-check"}
          onClick={onReview}
          disabled={saving}
        >
          {checked ? "Reopen" : "Mark checked"}
        </button>
      </div>
    </article>
  );
}

function Evidence({
  result,
  cell,
  records,
  saving,
  close,
  onPage,
  onPreview,
  onSave,
}: {
  result: Result;
  cell: Cell;
  records: SourceRecord[];
  saving: boolean;
  close: () => void;
  onPage: (page: number) => void;
  onPreview: (value: string) => Promise<PreviewReport>;
  onSave: (value: string, note: string) => void;
}) {
  const current = cellValue(result, cell);
  const hasSourceBox = records.some(
    (record) =>
      Array.isArray(record.bbox) &&
      record.bbox.length === 4 &&
      record.bbox.every((value) => Number.isFinite(value)) &&
      record.bbox[2] > record.bbox[0] &&
      record.bbox[3] > record.bbox[1],
  );
  const canEdit =
    cell.column <
    (cell.row < 0
      ? result.tables[cell.table].headers.length
      : (result.tables[cell.table].rows[cell.row]?.length ?? 0));
  const [value, setValue] = useState(current);
  const [note, setNote] = useState("");
  const [checked, setChecked] = useState(false);
  const [preview, setPreview] = useState<PreviewReport | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const proposal = result.proposals.find(
    (p) =>
      p.table === cell.table + 1 &&
      p.row === cell.row &&
      p.column === cell.column,
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canEdit && checked && note.trim() && value !== current)
      onSave(value, note);
  };
  const previewImpact = async (proposed: string) => {
    setPreviewing(true);
    setPreviewError("");
    setPreview(null);
    try {
      setPreview(await onPreview(proposed));
    } catch (error) {
      setPreviewError(message(error));
    } finally {
      setPreviewing(false);
    }
  };
  return (
    <section className="evidence-drawer" aria-labelledby="evidence-heading">
      <div className="evidence-heading">
        <div>
          <span className="evidence-icon">
            <Icon name="link" size={19} />
          </span>
          <div>
            <p className="eyebrow">CELL EVIDENCE</p>
            <h2 id="evidence-heading">
              {cell.row < 0 ? "Header" : `Row ${cell.row + 1}`} <span>/</span>{" "}
              {result.tables[cell.table].headers[cell.column] ??
                `Column ${cell.column + 1}`}
            </h2>
          </div>
        </div>
        <button
          className="icon-button"
          onClick={close}
          aria-label="Close cell evidence"
        >
          <Icon name="close" />
        </button>
      </div>
      <div className="evidence-body">
        <div className="readings">
          <div className="current-reading">
            <span>WORKING VALUE</span>
            <code>{current || "(empty)"}</code>
          </div>
          {records.length ? (
            <>
              <div className="reading-list">
                {records.map((r, i) => (
                  <button key={i} onClick={() => onPage(r.page)}>
                  <span className="reading-page">p.{r.page}</span>
                  <span>
                    <strong>{r.text || "(empty reading)"}</strong>
                    <small>
                      {r.engine ?? "extracted"}
                      {r.role === "comparison" ? " · alternative reading" : ""}
                      {r.role === "vertical_merge_expansion"
                        ? " · repeated from merged group cell"
                        : ""}
                      {r.initial_reading && r.initial_reading !== r.text
                        ? ` · first reading: ${r.initial_reading}`
                        : ""}
                    </small>
                  </span>
                  <span className="reading-score">
                    {r.confidence == null
                      ? r.engine?.startsWith("native")
                        ? "Native text"
                        : "Score unavailable"
                      : `${Math.round(r.confidence * 100)}% OCR score`}
                  </span>
                  <Icon name="eye" size={14} />
                  </button>
                ))}
              </div>
              {!hasSourceBox && (
                <p className="evidence-location-warning" role="status">
                  <Icon name="warning" size={15} /> The engine retained a source
                  reading but no exact cell box. Inspect the full source page before
                  accepting this value.
                </p>
              )}
            </>
          ) : (
            <p className="empty-note">
              No cell-level source record was produced. Compare the mapped full
              source page before accepting or editing this value.
            </p>
          )}
          <p className="disclosure">
            OCR recognition scores describe the engine’s reading, not measured
            extraction accuracy.
          </p>
          {proposal && (
            <details className="proposal-receipts" open>
              <summary>
                <Icon name="spark" size={15} /> Suggested value:{" "}
                <strong>{proposal.proposed}</strong> · {proposal.support_count}{" "}
                equations
              </summary>
              {proposal.supporting_equations.map((equation, i) => (
                <code key={i}>{equation}</code>
              ))}
              <p>
                Inspect the original. A consistent number may still change a
                source error.
              </p>
              <button
                className="secondary-button preview-button"
                disabled={previewing || saving}
                onClick={() => void previewImpact(proposal.proposed)}
              >
                {previewing ? <Spinner /> : <Icon name="eye" size={14} />}
                {previewing
                  ? "Checking disposable copy…"
                  : "Preview validation impact"}
              </button>
              {previewError && (
                <p className="field-error" role="alert">
                  {previewError}
                </p>
              )}
              {preview && (
                <div className="preview-impact" aria-live="polite">
                  <p>Preview only · working data unchanged</p>
                  <dl>
                    <div>
                      <dt>Review findings</dt>
                      <dd>
                        {preview.before.findings}
                        <Icon name="arrow" size={13} />
                        {preview.after.findings}
                      </dd>
                    </div>
                    <div>
                      <dt>Failed equation checks</dt>
                      <dd>
                        {preview.before.failed_equation_checks}
                        <Icon name="arrow" size={13} />
                        {preview.after.failed_equation_checks}
                      </dd>
                    </div>
                  </dl>
                  <small>
                    Fewer findings do not establish that the proposed value is
                    correct.
                  </small>
                </div>
              )}
              <button
                className="text-button"
                onClick={() => setValue(proposal.proposed)}
              >
                Use as reviewed value <Icon name="arrow" size={14} />
              </button>
            </details>
          )}
        </div>
        <form className="correction-form" onSubmit={submit}>
          <div className="form-title">
            <Icon name="eye" size={16} />
            <h3>Correct after checking the source</h3>
          </div>
          {!canEdit && (
            <p className="disclosure">
              This position was not extracted. Inspect the source; a missing
              cell cannot be replaced through a value correction.
            </p>
          )}
          <label>
            Reviewed value
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              disabled={saving}
            />
          </label>
          <label>
            Reason for this correction
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What did you confirm in the original?"
              rows={2}
              required
              disabled={saving}
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              required
              disabled={saving}
            />{" "}
            I checked this value against the source.
          </label>
          <div className="correction-footer">
            <span>Original readings stay in the audit.</span>
            <button
              className="primary-button"
              disabled={
                saving ||
                !canEdit ||
                !checked ||
                !note.trim() ||
                value === current
              }
            >
              {saving ? <Spinner /> : <Icon name="check" size={15} />}Save
              correction
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

function ReviewModal({
  result,
  saving,
  reviewed,
  pendingItems,
  onClose,
  onReview,
}: {
  result: Result;
  saving: boolean;
  reviewed: boolean;
  pendingItems: number;
  onClose: () => void;
  onReview: (note: string) => void;
}) {
  const [checked, setChecked] = useState(false);
  const [note, setNote] = useState("");
  return (
    <Modal
      title={reviewed ? "Source check recorded" : "Record a source check"}
      onClose={onClose}
    >
      {reviewed ? (
        <>
          <div className="review-success">
            <Icon name="shield" size={32} />
            <h3>This exact snapshot has a source-check attestation.</h3>
            <p>{result.review.note}</p>
          </div>
          <p className="disclosure">
            Any correction invalidates this source check. The attestation
            records a human review, not independently measured accuracy or
            reviewer identity.
          </p>
        </>
      ) : (
        <form
          className="review-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (checked && note.trim()) onReview(note);
          }}
        >
          <p>
            Review the original pages and the{" "}
            <strong>{pendingItems} pending priority items</strong> before
            recording your check. Every actionable item must be marked checked
            individually.
          </p>
          {pendingItems > 0 && (
            <p className="field-error" role="alert">
              Complete all {pendingItems} pending review items before recording
              the final source check.
            </p>
          )}
          <label className="check-label">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              required
              disabled={saving}
            />
            I checked the original source pages and reviewed the priority
            queue.
          </label>
          <label>
            Review note and accepted items
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              placeholder="What did you check? Which readings or findings did you accept, and why?"
              required
              disabled={saving}
            />
          </label>
          <p className="disclosure">
            This records your attestation for the current snapshot. It does not
            guarantee that the document or extraction is correct.
          </p>
          <button
            className="primary-button"
            disabled={saving || pendingItems > 0 || !checked || !note.trim()}
          >
            {saving ? <Spinner /> : <Icon name="shield" size={17} />}Record
            source check
          </button>
        </form>
      )}
    </Modal>
  );
}
