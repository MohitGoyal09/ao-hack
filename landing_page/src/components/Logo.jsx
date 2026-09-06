import logoImg from '../../logo.png'

export default function Logo({ size = 62, className = 'brand-mark' }) {
  return (
    <img
      src={logoImg}
      alt="RUX Logo"
      className={className}
      style={{
        width: `${size}px`,
        height: 'auto',
        maxHeight: `${size}px`,
        objectFit: 'contain',
        display: 'inline-block',
        verticalAlign: 'middle',
      }}
    />
  )
}
