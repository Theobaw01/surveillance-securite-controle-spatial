"use client";

import { useEffect, useState, useRef } from "react";
import {
  Users,
  UserPlus,
  Trash2,
  Upload,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { getPersons, registerPerson, deletePerson } from "@/lib/api";
import clsx from "clsx";

interface PersonRow {
  person_id: string;
  nom: string;
  prenom: string;
  groupe: string;
  role: string;
  organisation: string;
  created_at: string;
}

export default function PersonsPage() {
  const [persons, setPersons] = useState<PersonRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Form
  const [nom, setNom] = useState("");
  const [prenom, setPrenom] = useState("");
  const [groupe, setGroupe] = useState("");
  const [role, setRole] = useState("visiteur");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(
    null
  );
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const data = await getPersons();
      setPersons(data.persons);
      setTotal(data.total);
    } catch {
      // API maybe offline
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      setPhoto(file);
      setPreview(URL.createObjectURL(file));
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!photo || !nom || !prenom) return;

    setSubmitting(true);
    setMsg(null);
    try {
      const res = await registerPerson(photo, nom, prenom, groupe, role);
      setMsg({
        type: "ok",
        text: `${prenom} ${nom} enregistré(e) — ID: ${res.person_id} — Score visage: ${(res.face_score * 100).toFixed(0)}%`,
      });
      setNom("");
      setPrenom("");
      setGroupe("");
      setRole("visiteur");
      setPhoto(null);
      setPreview(null);
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err: unknown) {
      setMsg({
        type: "err",
        text: err instanceof Error ? err.message : "Erreur enregistrement",
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(personId: string) {
    if (!confirm(`Supprimer la personne ${personId} ?`)) return;
    try {
      await deletePerson(personId);
      load();
    } catch {
      alert("Erreur suppression");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users className="w-6 h-6" /> Personnes
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Enregistrez et gérez les personnes à reconnaître
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Registration form */}
        <div className="lg:col-span-1">
          <form
            onSubmit={handleRegister}
            className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-4"
          >
            <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
              <UserPlus className="w-4 h-4" />
              Enregistrer une personne
            </h3>

            {/* Photo upload */}
            <div
              className="border-2 border-dashed border-surface-border rounded-lg p-4 text-center cursor-pointer hover:border-brand-500 transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              {preview ? (
                <img
                  src={preview}
                  alt="Aperçu"
                  className="w-24 h-24 rounded-lg object-cover mx-auto"
                />
              ) : (
                <>
                  <Upload className="w-8 h-8 mx-auto text-gray-500 mb-2" />
                  <p className="text-xs text-gray-400">
                    Cliquez pour uploader une photo
                  </p>
                </>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <input
                type="text"
                placeholder="Prénom *"
                value={prenom}
                onChange={(e) => setPrenom(e.target.value)}
                required
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500"
              />
              <input
                type="text"
                placeholder="Nom *"
                value={nom}
                onChange={(e) => setNom(e.target.value)}
                required
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500"
              />
            </div>

            <input
              type="text"
              placeholder="Groupe (classe, département...)"
              value={groupe}
              onChange={(e) => setGroupe(e.target.value)}
              className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500"
            />

            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500"
            >
              <option value="visiteur">Visiteur</option>
              <option value="employe">Employé</option>
              <option value="eleve">Élève</option>
              <option value="professeur">Professeur</option>
              <option value="personnel">Personnel</option>
              <option value="vip">VIP</option>
              <option value="manager">Manager</option>
            </select>

            <button
              type="submit"
              disabled={submitting || !photo || !nom || !prenom}
              className="w-full py-2.5 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? "Enregistrement..." : "Enregistrer"}
            </button>

            {msg && (
              <div
                className={clsx(
                  "flex items-start gap-2 text-xs p-3 rounded-lg",
                  msg.type === "ok"
                    ? "bg-green-500/10 text-green-400"
                    : "bg-red-500/10 text-red-400"
                )}
              >
                {msg.type === "ok" ? (
                  <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                )}
                {msg.text}
              </div>
            )}
          </form>
        </div>

        {/* Person list */}
        <div className="lg:col-span-2">
          <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-surface-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-300">
                Personnes enregistrées
              </h3>
              <span className="text-xs text-gray-500">
                {total} personne(s)
              </span>
            </div>

            {loading ? (
              <div className="p-8 text-center text-sm text-gray-500">
                Chargement...
              </div>
            ) : persons.length === 0 ? (
              <div className="p-8 text-center text-sm text-gray-500">
                Aucune personne enregistrée.
                <br />
                Utilisez le formulaire pour en ajouter.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] text-gray-400 uppercase tracking-wider border-b border-surface-border">
                      <th className="px-4 py-3">ID</th>
                      <th className="px-4 py-3">Nom</th>
                      <th className="px-4 py-3">Groupe</th>
                      <th className="px-4 py-3">Rôle</th>
                      <th className="px-4 py-3">Date</th>
                      <th className="px-4 py-3 w-12"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-border">
                    {persons.map((p) => (
                      <tr
                        key={p.person_id}
                        className="hover:bg-surface-hover/40 transition-colors"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-gray-400">
                          {p.person_id}
                        </td>
                        <td className="px-4 py-3 text-gray-200 font-medium">
                          {p.prenom} {p.nom}
                        </td>
                        <td className="px-4 py-3 text-gray-400">
                          {p.groupe || "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs bg-brand-600/20 text-brand-200 px-2 py-0.5 rounded-full">
                            {p.role}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {p.created_at ? p.created_at.slice(0, 10) : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleDelete(p.person_id)}
                            className="text-gray-500 hover:text-red-400 transition-colors"
                            title="Supprimer"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
