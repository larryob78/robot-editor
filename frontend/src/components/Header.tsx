import "./Header.css";

export const Header = () => (
  <header className="header">
    <div className="header__brand">
      <span className="header__logo">LC</span>
      <div>
        <h1>LuminaCut AI</h1>
        <p>Agentic natural-language video editing</p>
      </div>
    </div>
    <nav className="header__actions">
      <a href="https://github.com" target="_blank" rel="noreferrer">
        Docs
      </a>
      <a href="mailto:product@luminacut.ai">Support</a>
    </nav>
  </header>
);

export default Header;
