// A plain-language error box, announced to screen readers when it appears.
import { Icon } from "./Icon";
import "./ErrorMessage.css";

/** Props of the error box: the message to show. */
interface ErrorMessageProps {
  message: string;
}

/** Show an error message with an icon, as an alert. */
export function ErrorMessage({ message }: ErrorMessageProps) {
  return (
    <div className="error-message" role="alert">
      <Icon name="cross-circle" size={20} />
      <span>{message}</span>
    </div>
  );
}
