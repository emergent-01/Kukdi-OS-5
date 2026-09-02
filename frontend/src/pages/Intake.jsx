import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Plus, ExternalLink, Check } from "lucide-react";
import { api } from "../lib/api";
import { Field, inputClass, PrimaryButton } from "../components/Modal";

const COMPETENCIES = [
  "Leadership", "Ambiguity", "Failure", "Conflict", "Influence",
  "Execution", "Analytical Thinking", "Customer Focus",
];
const EVENT_TYPES = ["class", "deadline", "exam", "event", "task", "placement"];
const PREP_CATEGORIES = ["roadmap", "framework", "story", "case", "resume", "networking", "daily"];

const fade = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.7, ease: [0.22, 1, 0.36, 1] } };
const Label = ({ children }) => (
  <h2 className="text-xs tracking-[0.18em] uppercase text-[#8A8F8C] mb-6">{children}</h2>
);

export default function Intake() {
  const [candidates, setCandidates] = useState([]);
  const [edits, setEdits] = useState({}); // id -> {prep_group, strengths[], strength_note}
  const [newPerson, setNewPerson] = useState("");
  const [mentors, setMentors] = useState([]);
  const [mentorDraft, setMentorDraft] = useState("");
  const [events, setEvents] = useState([]);
  const [eventDraft, setEventDraft] = useState({ title: "", start: "", type: "event", notes: "" });
  const [stories, setStories] = useState([]);
  const [storyDraft, setStoryDraft] = useState({ title: "", situation: "", task: "", action: "", result: "" });
  const [prep, setPrep] = useState([]);
  const [prepDraft, setPrepDraft] = useState({ title: "", category: "roadmap", content: "" });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const loadPeople = () =>
    api.people().then((d) => setCandidates((d.people || []).filter((p) => p.relation === "Peer / prep group")));
  useEffect(() => { loadPeople(); }, []);

  const editOf = (p) => edits[p.id] || { prep_group: !!p.prep_group, strengths: p.strengths || [], strength_note: p.strength_note || "" };
  const setEdit = (id, patch) => setEdits((e) => ({ ...e, [id]: { ...editOf({ id, ...(e[id] || {}) }), ...patch } }));

  const toggleConfirm = (p) => { const c = editOf(p); setEdit(p.id, { prep_group: !c.prep_group }); };
  const toggleChip = (p, comp) => {
    const c = editOf(p);
    const has = c.strengths.includes(comp);
    setEdit(p.id, { strengths: has ? c.strengths.filter((x) => x !== comp) : [...c.strengths, comp] });
  };

  const addPerson = async () => {
    if (!newPerson.trim()) return;
    await api.createPerson({ name: newPerson.trim(), relation: "Peer / prep group" });
    setNewPerson("");
    loadPeople();
  };

  const addTo = (setter, draft, resetDraft, valid) => { if (valid) { setter((a) => [...a, draft]); resetDraft(); } };

  const save = async () => {
    setSaving(true);
    try {
      const people_updates = candidates
        .map((p) => ({ id: p.id, ...editOf(p) }))
        .filter((u) => edits[u.id]);
      await api.intakeCommit({ events, stories, prep_items: prep, mentors, people_updates });
      setSaved(true);
      loadPeople();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="intake-page">
      <span className="text-xs tracking-[0.18em] uppercase text-[#8A8F8C]">Day one</span>
      <h1 className="font-editorial text-5xl md:text-6xl text-[#2C2D2B] mt-2 mb-4">Let's set up your world</h1>
      <p className="text-[#5C605A] max-w-xl mb-16 leading-relaxed">
        Add as much or as little as feels right — nothing here is required, and you can come back anytime. Kukdi will hold whatever you give it.
      </p>

      {/* PREP CIRCLE */}
      <motion.section {...fade} className="mb-20" data-testid="intake-prep-circle">
        <Label>Your prep circle</Label>
        <div className="space-y-8">
          {candidates.map((p) => {
            const c = editOf(p);
            return (
              <div key={p.id} className="border-b border-[#E2DFD8] pb-8">
                <div className="flex items-center justify-between">
                  <span className="font-editorial text-2xl text-[#2C2D2B]">{p.name}</span>
                  <button
                    onClick={() => toggleConfirm(p)}
                    data-testid={`intake-person-confirm-${p.id}`}
                    className={`flex items-center gap-2 text-xs tracking-[0.12em] uppercase px-4 py-2 rounded-full transition-colors ${c.prep_group ? "bg-[#9DB0A3] text-[#F7F6F2]" : "bg-[#EFECE7] text-[#8A8F8C] hover:text-[#2C2D2B]"}`}
                  >
                    {c.prep_group ? <Check size={13} strokeWidth={2} /> : null}
                    {c.prep_group ? "In your circle" : "Confirm"}
                  </button>
                </div>
                <div className="flex flex-wrap gap-2 mt-4">
                  {COMPETENCIES.map((comp) => {
                    const on = c.strengths.includes(comp);
                    return (
                      <button
                        key={comp}
                        onClick={() => toggleChip(p, comp)}
                        data-testid={`intake-person-strength-chip-${comp}`}
                        className={`text-xs px-3 py-1.5 rounded-full transition-colors ${on ? "bg-[#D4DDD7] text-[#2C2D2B]" : "bg-[#EFECE7] text-[#8A8F8C] hover:text-[#5C605A]"}`}
                      >
                        {comp}
                      </button>
                    );
                  })}
                </div>
                <input
                  className={`${inputClass} mt-4`}
                  placeholder="Strong at… (a quiet note)"
                  value={c.strength_note}
                  onChange={(e) => setEdit(p.id, { strength_note: e.target.value })}
                  data-testid={`intake-person-note-${p.id}`}
                />
              </div>
            );
          })}
        </div>
        <div className="flex gap-3 mt-8">
          <input className={inputClass} placeholder="Add someone new" value={newPerson} onChange={(e) => setNewPerson(e.target.value)} data-testid="intake-add-person-input" />
          <button onClick={addPerson} data-testid="intake-add-person" className="shrink-0 flex items-center gap-1.5 text-sm text-[#5C605A] hover:text-[#2C2D2B] transition-colors px-3">
            <Plus size={15} strokeWidth={1.5} /> Add
          </button>
        </div>
      </motion.section>

      {/* MENTORS */}
      <motion.section {...fade} className="mb-20" data-testid="intake-mentors">
        <Label>Mentors</Label>
        <p className="text-[#5C605A] max-w-xl mb-5 leading-relaxed">
          If it helps, wander the{" "}
          <a href="https://isb.almaconnect.com/directory/filter/product-management-professionals-3" target="_blank" rel="noreferrer" data-testid="intake-alumni-link" className="text-[#5C605A] underline decoration-[#9DB0A3] hover:text-[#2C2D2B] inline-flex items-center gap-1">
            ISB PM alumni directory <ExternalLink size={13} strokeWidth={1.5} />
          </a>{" "}
          and add anyone you'd like to reach out to. No rush — a name or two is plenty.
        </p>
        {mentors.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {mentors.map((m, i) => <span key={`${m.name}-${i}`} className="text-sm text-[#5C605A] bg-[#EFECE7] rounded-full px-4 py-1.5">{m.name}</span>)}
          </div>
        )}
        <div className="flex gap-3">
          <input className={inputClass} placeholder="Mentor's name" value={mentorDraft} onChange={(e) => setMentorDraft(e.target.value)} data-testid="intake-mentor-input" />
          <button onClick={() => addTo(setMentors, { name: mentorDraft.trim() }, () => setMentorDraft(""), mentorDraft.trim())} data-testid="intake-add-mentor" className="shrink-0 flex items-center gap-1.5 text-sm text-[#5C605A] hover:text-[#2C2D2B] transition-colors px-3">
            <Plus size={15} strokeWidth={1.5} /> Add
          </button>
        </div>
      </motion.section>

      {/* WHAT'S AHEAD */}
      <motion.section {...fade} className="mb-20" data-testid="intake-events">
        <Label>What's ahead</Label>
        {events.length > 0 && (
          <div className="space-y-2 mb-5">
            {events.map((e, i) => <div key={`${e.title}-${i}`} className="text-[#5C605A]"><span className="text-[#2C2D2B]">{e.title}</span> · {e.type} · {e.start}</div>)}
          </div>
        )}
        <div className="space-y-3">
          <Field label="Title"><input className={inputClass} value={eventDraft.title} onChange={(e) => setEventDraft({ ...eventDraft, title: e.target.value })} data-testid="intake-event-title" /></Field>
          <div className="flex flex-col sm:flex-row gap-3">
            <input type="datetime-local" className={inputClass} value={eventDraft.start} onChange={(e) => setEventDraft({ ...eventDraft, start: e.target.value })} data-testid="intake-event-start" />
            <select className={inputClass} value={eventDraft.type} onChange={(e) => setEventDraft({ ...eventDraft, type: e.target.value })} data-testid="intake-event-type">
              {EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <input className={inputClass} placeholder="Notes (optional)" value={eventDraft.notes} onChange={(e) => setEventDraft({ ...eventDraft, notes: e.target.value })} data-testid="intake-event-notes" />
          <button onClick={() => addTo(setEvents, { ...eventDraft, start: eventDraft.start ? new Date(eventDraft.start).toISOString() : "" }, () => setEventDraft({ title: "", start: "", type: "event", notes: "" }), eventDraft.title.trim() && eventDraft.start)} data-testid="intake-add-event" className="flex items-center gap-1.5 text-sm text-[#5C605A] hover:text-[#2C2D2B] transition-colors">
            <Plus size={15} strokeWidth={1.5} /> Add date
          </button>
        </div>
      </motion.section>

      {/* STORIES */}
      <motion.section {...fade} className="mb-20" data-testid="intake-stories">
        <Label>Your stories</Label>
        {stories.length > 0 && (
          <div className="space-y-2 mb-5">
            {stories.map((s, i) => <div key={`${s.title}-${i}`} className="text-[#2C2D2B]">{s.title}</div>)}
          </div>
        )}
        <div className="space-y-3">
          <Field label="Title"><input className={inputClass} value={storyDraft.title} onChange={(e) => setStoryDraft({ ...storyDraft, title: e.target.value })} data-testid="intake-story-title" /></Field>
          {[["situation", "Situation"], ["task", "Task"], ["action", "Action"], ["result", "Result"]].map(([k, l]) => (
            <Field key={k} label={`${l} (optional)`}><textarea className={inputClass} rows={2} value={storyDraft[k]} onChange={(e) => setStoryDraft({ ...storyDraft, [k]: e.target.value })} data-testid={`intake-story-${k}`} /></Field>
          ))}
          <button onClick={() => addTo(setStories, storyDraft, () => setStoryDraft({ title: "", situation: "", task: "", action: "", result: "" }), storyDraft.title.trim())} data-testid="intake-add-story" className="flex items-center gap-1.5 text-sm text-[#5C605A] hover:text-[#2C2D2B] transition-colors">
            <Plus size={15} strokeWidth={1.5} /> Add story
          </button>
        </div>
      </motion.section>

      {/* PREP */}
      <motion.section {...fade} className="mb-20" data-testid="intake-prep">
        <Label>What you're preparing</Label>
        {prep.length > 0 && (
          <div className="space-y-2 mb-5">
            {prep.map((p, i) => <div key={`${p.title}-${i}`} className="text-[#5C605A]"><span className="text-[#2C2D2B]">{p.title}</span> · {p.category}</div>)}
          </div>
        )}
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <input className={inputClass} placeholder="What are you working on?" value={prepDraft.title} onChange={(e) => setPrepDraft({ ...prepDraft, title: e.target.value })} data-testid="intake-prep-title" />
            <select className={inputClass} value={prepDraft.category} onChange={(e) => setPrepDraft({ ...prepDraft, category: e.target.value })} data-testid="intake-prep-category">
              {PREP_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <input className={inputClass} placeholder="A note (optional)" value={prepDraft.content} onChange={(e) => setPrepDraft({ ...prepDraft, content: e.target.value })} data-testid="intake-prep-content" />
          <button onClick={() => addTo(setPrep, prepDraft, () => setPrepDraft({ title: "", category: "roadmap", content: "" }), prepDraft.title.trim())} data-testid="intake-add-prep" className="flex items-center gap-1.5 text-sm text-[#5C605A] hover:text-[#2C2D2B] transition-colors">
            <Plus size={15} strokeWidth={1.5} /> Add
          </button>
        </div>
      </motion.section>

      <motion.div {...fade} className="border-t border-[#E2DFD8] pt-10">
        <PrimaryButton onClick={save} data-testid="intake-save" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </PrimaryButton>
        {saved && (
          <p className="font-editorial text-2xl italic text-[#5C605A] mt-6 max-w-xl leading-snug" data-testid="intake-saved">
            I've got all of this now — your circle, your dates, the stories you're shaping. Come back and add more whenever it comes to you.
          </p>
        )}
      </motion.div>
    </div>
  );
}
