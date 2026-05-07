/**
 * Datasets list + upload — /datasets
 *
 * Lists all registered datasets with status badges.
 * Upload button triggers the multipart POST and then polls until
 * status transitions off 'uploading'. When it reaches 'mapping',
 * navigates to the dataset detail page for schema mapping.
 */

import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDatasets, useUploadDataset } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { StatusBadge } from '@/components/StatusBadge'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { formatRelativeDate } from '@/lib/formatters'
import { Database, Upload, X } from 'lucide-react'
import type { LicenseTag } from '@/api/types'

export function DatasetsPage() {
  const navigate = useNavigate()
  const { data, isLoading, isError, error, refetch } = useDatasets({ limit: 50 })
  const uploadMutation = useUploadDataset()

  const [showUploadForm, setShowUploadForm] = useState(false)
  const [uploadName, setUploadName] = useState('')
  const [uploadDesc, setUploadDesc] = useState('')
  const [licenseTag, setLicenseTag] = useState<LicenseTag>('open')
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState<'idle' | 'uploading' | 'done'>('idle')
  const fileRef = useRef<HTMLInputElement>(null)

  const datasets = data?.data ?? []

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file || !uploadName.trim()) return

    setUploadError(null)
    setUploadProgress('uploading')

    const form = new FormData()
    form.append('file', file)
    form.append('name', uploadName.trim())
    form.append('description', uploadDesc.trim())
    form.append('license_tag', licenseTag)

    try {
      const result = await uploadMutation.mutateAsync(form)
      setUploadProgress('done')
      setShowUploadForm(false)
      // Navigate to the dataset detail page for polling + schema mapping
      navigate(`/datasets/${result.dataset_id}`)
    } catch (err) {
      setUploadProgress('idle')
      setUploadError(
        err instanceof Error ? err.message : 'Upload failed — please try again.'
      )
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Datasets</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Upload and manage feature datasets for experiments
          </p>
        </div>
        <Button size="sm" onClick={() => setShowUploadForm((v) => !v)}>
          <Upload className="mr-2 h-4 w-4" />
          Upload dataset
        </Button>
      </div>

      {/* Inline upload form */}
      {showUploadForm && (
        <Card className="border-dashed">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Upload new dataset</CardTitle>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowUploadForm(false)}
                aria-label="Close upload form"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <CardDescription>
              CSV, Excel (.xlsx), or JSON — max 50 MB
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={(e) => void handleUpload(e)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ds-name">Dataset name *</Label>
                <Input
                  id="ds-name"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                  placeholder="e.g. Receiver separation 2020-2024"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ds-desc">Description</Label>
                <Textarea
                  id="ds-desc"
                  value={uploadDesc}
                  onChange={(e) => setUploadDesc(e.target.value)}
                  placeholder="What does this dataset contain? Where did it come from?"
                  rows={2}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ds-license">License</Label>
                <Select
                  id="ds-license"
                  value={licenseTag}
                  onChange={(e) => setLicenseTag(e.target.value as LicenseTag)}
                >
                  <option value="open">Open</option>
                  <option value="licensed_commercial">Licensed (commercial)</option>
                  <option value="personal_use_only">Personal use only</option>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ds-file">File *</Label>
                <Input
                  id="ds-file"
                  ref={fileRef}
                  type="file"
                  accept=".csv,.xlsx,.json"
                  required
                />
              </div>

              {uploadError && (
                <Alert variant="destructive">
                  <AlertDescription>{uploadError}</AlertDescription>
                </Alert>
              )}

              {uploadProgress === 'uploading' && (
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">Uploading…</p>
                  <Progress value={null} className="animate-pulse" />
                </div>
              )}

              <div className="flex gap-2 justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowUploadForm(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={uploadProgress === 'uploading' || !uploadName.trim()}
                >
                  <Upload className="mr-2 h-4 w-4" />
                  Upload
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Dataset list */}
      {isLoading && <LoadingState rows={4} />}

      {isError && (
        <ErrorState
          error={error}
          context="datasets"
          onRetry={() => void refetch()}
        />
      )}

      {!isLoading && !isError && datasets.length === 0 && (
        <EmptyState
          icon={Database}
          title="No datasets yet"
          description="Upload a CSV, Excel, or JSON file to start building custom feature experiments."
          action={
            <Button size="sm" onClick={() => setShowUploadForm(true)}>
              <Upload className="mr-2 h-4 w-4" />
              Upload your first dataset
            </Button>
          }
        />
      )}

      {!isLoading && !isError && datasets.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {datasets.map((ds) => (
            <Link key={ds.dataset_id} to={`/datasets/${ds.dataset_id}`} className="block group">
              <Card className="h-full transition-shadow group-hover:shadow-md">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base leading-tight">{ds.name}</CardTitle>
                    <StatusBadge status={ds.status} />
                  </div>
                  <CardDescription className="line-clamp-2">{ds.description || '—'}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                    <span>{ds.row_count.toLocaleString()} rows</span>
                    <span>{ds.column_count} columns</span>
                    <span>Join: {ds.join_key_type}</span>
                    <span>{ds.license_tag}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {formatRelativeDate(ds.upload_date)}
                    {ds.schema_source === 'ai_assisted' && (
                      <span className="ml-2 text-blue-600">AI-mapped</span>
                    )}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
