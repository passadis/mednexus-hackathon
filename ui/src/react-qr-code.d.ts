declare module 'react-qr-code' {
  import { ComponentType, SVGProps } from 'react';
  interface QRCodeProps extends SVGProps<SVGSVGElement> {
    value: string;
    size?: number;
    level?: 'L' | 'M' | 'Q' | 'H';
    bgColor?: string;
    fgColor?: string;
  }
  const QRCode: ComponentType<QRCodeProps>;
  export default QRCode;
}
