// Indian numbering system Rupee formatter (e.g. ₹10,230.00, ₹11,48,220.00)
export function formatINR(val, decimals = 2) {
  if (val === undefined || val === null || isNaN(val)) return '₹0.00'
  const num = Number(val)
  const isNegative = num < 0
  const absNum = Math.abs(num)
  const fixed = absNum.toFixed(decimals)
  const [intPart, decPart] = fixed.split('.')

  const lastThree = intPart.substring(intPart.length - 3)
  const otherNumbers = intPart.substring(0, intPart.length - 3)
  const formattedOther = otherNumbers !== '' ? otherNumbers.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' : ''
  const decString = decimals > 0 ? `.${decPart}` : ''
  return `${isNegative ? '-' : ''}₹${formattedOther}${lastThree}${decString}`
}

export function formatNumber(val, decimals = 0) {
  if (val === undefined || val === null || isNaN(val)) return '0'
  const num = Number(val)
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

