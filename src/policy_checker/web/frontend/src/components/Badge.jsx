export default function Badge({ type, children }) {
  const cls = `badge badge-${type || 'info'}`
  return <span className={cls}>{children || type}</span>
}
